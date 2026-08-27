import threading
import time
from typing import Dict, Optional

class BiometricBindingManager:
    """
    Manages temporary, runtime-only bindings between Vision tracking IDs (TRACK-*)
    and Authoritative Person IDs (ATLAS-P-*).
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._bindings: Dict[str, str] = {}
        self._last_seen: Dict[str, float] = {}

    def bind(self, track_id: str, person_id: str) -> bool:
        """
        Create a temporary mapping. person_id must be authoritative.
        """
        if not str(track_id).startswith("TRACK-"):
            return False
        if not str(person_id).startswith("ATLAS-P-"):
            return False
            
        with self._lock:
            self._bindings[track_id] = person_id
            self._last_seen[track_id] = time.time()
            return True

    def resolve(self, track_id: str) -> Optional[str]:
        """
        Returns the mapped ATLAS-P-* ID if it exists, updating last_seen.
        """
        with self._lock:
            if track_id in self._bindings:
                self._last_seen[track_id] = time.time()
                return self._bindings[track_id]
            return None

    def cleanup_stale_tracks(self, timeout_seconds: float = 60.0):
        """
        Removes bindings that haven't been resolved recently.
        """
        with self._lock:
            now = time.time()
            stale = [tid for tid, last in self._last_seen.items() if (now - last) > timeout_seconds]
            for tid in stale:
                self._bindings.pop(tid, None)
                self._last_seen.pop(tid, None)
                
    def get_all_bindings(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._bindings)
