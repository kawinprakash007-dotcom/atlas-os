from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class AuditRecord:
    # ── EXISTING FIELDS (preserved order & types) ──────────────────────────
    attempt_id: str                           # UUID — also used as event_id
    timestamp: float
    event_type: str  # LOGIN_SUCCESS | LOGIN_FAILED | BIOMETRIC_VERIFICATION_STARTED |
                     # BIOMETRIC_VERIFICATION_SUCCESS | BIOMETRIC_VERIFICATION_FAILED |
                     # LOGOUT | SESSION_EXPIRED | FACE_ENROLLMENT_STARTED |
                     # FACE_ENROLLMENT_COMPLETED | FACE_ENROLLMENT_RESET |
                     # USER_CREATED | ACCOUNT_DISABLED | ACCOUNT_ENABLED | ACCESS_DENIED
    account_id: Optional[str] = None
    credential_verified: bool = False
    face_verified: bool = False
    access_result: str = "FAILURE"            # SUCCESS | FAILURE
    role: Optional[str] = None
    failure_category: Optional[str] = None   # INVALID_CREDENTIALS | FACE_VERIFICATION_FAILED | …

    # ── EXTENDED IDENTITY CONTEXT ──────────────────────────────────────────
    person_id: Optional[str] = None
    username: Optional[str] = None
    session_id: Optional[str] = None

    # ── NETWORK & DEVICE ───────────────────────────────────────────────────
    ip_address: Optional[str] = None
    device_info: Optional[str] = None        # User-Agent string or device hint

    # ── GEOLOCATION ────────────────────────────────────────────────────────
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_accuracy: Optional[float] = None     # metres

    # ── BIOMETRIC EVIDENCE ─────────────────────────────────────────────────
    biometric_score: Optional[float] = None  # cosine similarity [0-1]
    verification_result: Optional[str] = None  # MATCH | NO_MATCH | NO_FACE | …

    # ── EXTENSIBILITY ──────────────────────────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)

