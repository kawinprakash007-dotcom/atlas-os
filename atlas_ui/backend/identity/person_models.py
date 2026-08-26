from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

@dataclass
class Person:
    # ── CORE IDENTITY (existing — preserved order & defaults) ──────────────
    atlas_person_id: str
    display_name: str
    account_id: Optional[str] = None
    role: Optional[str] = None
    status: str = "ACTIVE"           # ACTIVE | DISABLED | REVOKED
    face_enrollment_status: str = "PENDING"  # PENDING | NOT_ENROLLED | ENROLLING | ENROLLED | FAILED | REVOKED
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ── ACCESS ACTIVITY ────────────────────────────────────────────────────
    first_login: Optional[float] = None
    last_login: Optional[float] = None
    login_count: int = 0
    last_logout: Optional[float] = None
    total_session_duration: float = 0.0   # cumulative seconds across all sessions

    # ── BIOMETRIC STATE ────────────────────────────────────────────────────
    enrolled_at: Optional[float] = None          # epoch timestamp of successful enrollment
    template_count: int = 0
    last_biometric_verification: Optional[float] = None
    last_verification_status: Optional[str] = None  # MATCH | NO_MATCH | NO_FACE | QUALITY_REJECT | …

    # ── LAST ACCESS INFORMATION ────────────────────────────────────────────
    last_access_timestamp: Optional[float] = None
    last_access_ip: Optional[str] = None
    last_access_device: Optional[str] = None     # User-Agent or device hint if available
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_accuracy: Optional[float] = None         # metres
    location_permission: Optional[str] = None    # granted | denied | prompt | unavailable

    # ── VERIFICATION EVIDENCE ──────────────────────────────────────────────
    latest_verification_snapshot: Optional[str] = None   # data URI (JPEG, small thumbnail)
    latest_verification_timestamp: Optional[float] = None
    latest_verification_result: Optional[str] = None
    latest_verification_score: Optional[float] = None   # cosine similarity [0-1]

    # ── SECURITY STATE ─────────────────────────────────────────────────────
    failed_login_attempts: int = 0
    last_failed_login: Optional[float] = None
    account_lock_status: bool = False            # True = locked out
    recent_security_events: List[Dict[str, Any]] = field(default_factory=list)

