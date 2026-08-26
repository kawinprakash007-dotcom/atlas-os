import uuid
import time
import copy
from typing import List, Optional, Dict, Any
from atlas_ui.backend.models.audit import AuditRecord

class AuthenticationAudit:
    def __init__(self):
        self._records: List[AuditRecord] = []

    def log_attempt(
        self,
        event_type: str,
        # ── existing params (keyword-only, all optional) ─────────────────
        account_id: Optional[str] = None,
        credential_verified: bool = False,
        face_verified: bool = False,
        access_result: str = "FAILURE",
        role: Optional[str] = None,
        failure_category: Optional[str] = None,
        # ── extended identity context ────────────────────────────────────
        person_id: Optional[str] = None,
        username: Optional[str] = None,
        session_id: Optional[str] = None,
        # ── network & device ─────────────────────────────────────────────
        ip_address: Optional[str] = None,
        device_info: Optional[str] = None,
        # ── geolocation ──────────────────────────────────────────────────
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        gps_accuracy: Optional[float] = None,
        # ── biometric evidence ────────────────────────────────────────────
        biometric_score: Optional[float] = None,
        verification_result: Optional[str] = None,
        # ── extensibility ─────────────────────────────────────────────────
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """
        Logs a security/activity event. Enforces that no passwords, hashes,
        or raw biometric embeddings are ever stored in the audit trail.

        All parameters beyond event_type are optional so every existing
        call site continues to work without modification.
        """
        record = AuditRecord(
            attempt_id=str(uuid.uuid4()),
            timestamp=time.time(),
            event_type=event_type,
            account_id=account_id,
            credential_verified=credential_verified,
            face_verified=face_verified,
            access_result=access_result,
            role=role,
            failure_category=failure_category,
            person_id=person_id,
            username=username,
            session_id=session_id,
            ip_address=ip_address,
            device_info=device_info,
            gps_latitude=gps_latitude,
            gps_longitude=gps_longitude,
            gps_accuracy=gps_accuracy,
            biometric_score=biometric_score,
            verification_result=verification_result,
            metadata=dict(metadata) if metadata else {},
        )
        self._records.append(record)
        return copy.deepcopy(record)

    def list_records(self) -> List[AuditRecord]:
        """Returns all records in chronological order."""
        return [copy.deepcopy(r) for r in self._records]

    def filter_records(
        self,
        event_type: Optional[str] = None,
        account_id: Optional[str] = None,
        person_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[AuditRecord]:
        """Returns filtered records, newest-first, capped at limit."""
        results = []
        for r in reversed(self._records):
            if event_type and r.event_type != event_type:
                continue
            if account_id and r.account_id != account_id:
                continue
            if person_id and r.person_id != person_id:
                continue
            results.append(copy.deepcopy(r))
            if len(results) >= limit:
                break
        return results

