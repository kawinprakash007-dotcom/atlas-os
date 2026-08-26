"""
VerificationSnapshotStore — thread-safe in-memory store for biometric verification
snapshots.

Design principles
-----------------
* One deque per person_id, capped at MAX_PER_PERSON entries (oldest evicted).
* Global flat index by snapshot_id for O(1) single-snapshot lookup.
* A single RLock guards all mutations; reads also hold the lock to prevent
  inconsistency during concurrent eviction.
* store() catches and logs all internal exceptions — it NEVER raises to the caller,
  so a storage failure can never affect the biometric verification outcome.
* No disk I/O.  Lifecycle matches the FastAPI process (same as AuthenticationAudit).
"""

import copy
import threading
from collections import deque
from typing import Dict, Deque, List, Optional

from atlas_ui.backend.models.snapshot import VerificationSnapshot


class VerificationSnapshotStore:
    """
    Per-person capped history of VerificationSnapshot records.

    Thread-safe via a single reentrant lock.
    """

    MAX_PER_PERSON: int = 50

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        # person_id  → deque of VerificationSnapshot (newest at right)
        self._by_person: Dict[str, Deque[VerificationSnapshot]] = {}
        # snapshot_id → VerificationSnapshot (fast lookup by id)
        self._by_id: Dict[str, VerificationSnapshot] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store(self, snapshot: VerificationSnapshot) -> Optional[str]:
        """
        Persist a snapshot record.

        Returns the snapshot_id on success, or None if an internal error occurs.
        Never raises — all exceptions are swallowed and logged to stdout.
        """
        try:
            with self._lock:
                q = self._by_person.setdefault(snapshot.person_id, deque())
                # Evict the oldest entry when the cap is reached
                if len(q) >= self.MAX_PER_PERSON:
                    oldest = q.popleft()
                    self._by_id.pop(oldest.snapshot_id, None)
                q.append(snapshot)
                self._by_id[snapshot.snapshot_id] = snapshot
            print(
                f"[SNAPSHOT STORE] Stored snapshot {snapshot.snapshot_id} "
                f"for person={snapshot.person_id} result={snapshot.result} "
                f"score={snapshot.score:.4f}",
                flush=True,
            )
            return snapshot.snapshot_id
        except Exception as exc:
            print(f"[SNAPSHOT STORE] store() failed (non-fatal): {exc}", flush=True)
            return None

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, snapshot_id: str) -> Optional[VerificationSnapshot]:
        """Return the snapshot for the given ID, or None if not found."""
        with self._lock:
            snap = self._by_id.get(snapshot_id)
            return copy.copy(snap) if snap is not None else None

    def list_for_person(
        self,
        person_id: str,
        include_image: bool = False,
    ) -> List[dict]:
        """
        Return a list of snapshot metadata dicts for a person, newest-first.

        When include_image=False (default), thumbnail_b64 is omitted from every
        dict to keep list responses lean.
        """
        with self._lock:
            q = self._by_person.get(person_id, deque())
            results = []
            for snap in reversed(q):           # newest-first
                d: dict = {
                    "snapshot_id":  snap.snapshot_id,
                    "person_id":    snap.person_id,
                    "account_id":   snap.account_id,
                    "session_id":   snap.session_id,
                    "timestamp":    snap.timestamp,
                    "result":       snap.result,
                    "score":        snap.score,
                    "has_thumbnail": snap.thumbnail_b64 is not None,
                }
                if include_image:
                    d["thumbnail_b64"] = snap.thumbnail_b64
                results.append(d)
            return results

    # ------------------------------------------------------------------
    # Admin / Maintenance
    # ------------------------------------------------------------------

    def clear_for_person(self, person_id: str) -> int:
        """
        Remove all snapshots for a person.

        Returns the number of records removed.
        """
        with self._lock:
            q = self._by_person.pop(person_id, deque())
            for snap in q:
                self._by_id.pop(snap.snapshot_id, None)
            return len(q)

    def total_count(self) -> int:
        """Total snapshots across all persons."""
        with self._lock:
            return len(self._by_id)

    def person_count(self, person_id: str) -> int:
        """Snapshot count for a specific person."""
        with self._lock:
            return len(self._by_person.get(person_id, deque()))
