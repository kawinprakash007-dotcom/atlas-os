from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class AdminUserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    enabled: bool = True

class AdminUserStatusUpdateRequest(BaseModel):
    enabled: bool

class UnifiedUserResponse(BaseModel):
    # ── IDENTITY ──────────────────────────────────────────────────────────
    account_id: str
    username: str
    role: str
    enabled: bool
    atlas_person_id: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[float] = None
    last_updated: Optional[float] = None

    # ── BIOMETRIC STATUS ──────────────────────────────────────────────────
    face_enrollment_status: str = "NOT_ENROLLED"
    enrolled_at: Optional[float] = None
    template_count: int = 0
    last_biometric_verification: Optional[float] = None
    last_verification_status: Optional[str] = None

    # ── ACCESS ACTIVITY ───────────────────────────────────────────────────
    first_login: Optional[float] = None
    last_login: Optional[float] = None
    login_count: int = 0
    current_session_status: str = "OFFLINE"     # ONLINE | OFFLINE
    current_session_id: Optional[str] = None
    last_logout: Optional[float] = None
    total_session_duration: float = 0.0
    last_activity: Optional[float] = None
    active_sessions: int = 0
    online: bool = False

    # ── LAST ACCESS INFORMATION ───────────────────────────────────────────
    last_access_timestamp: Optional[float] = None
    last_access_ip: Optional[str] = None
    last_access_device: Optional[str] = None
    gps_latitude: Optional[float] = None
    gps_longitude: Optional[float] = None
    gps_accuracy: Optional[float] = None
    location_permission: Optional[str] = None

    # ── VERIFICATION EVIDENCE ─────────────────────────────────────────────
    latest_verification_snapshot: Optional[str] = None
    latest_verification_timestamp: Optional[float] = None
    latest_verification_result: Optional[str] = None
    latest_verification_score: Optional[float] = None

    # ── SECURITY ──────────────────────────────────────────────────────────
    failed_login_attempts: int = 0
    last_failed_login: Optional[float] = None
    account_lock_status: bool = False
    recent_security_events: List[Dict[str, Any]] = Field(default_factory=list)

    # ── RISK ASSESSMENT ───────────────────────────────────────────────────
    risk_level: str = "LOW"
    risk_reasons: List[str] = Field(default_factory=list)

class UnifiedUserListResponse(BaseModel):
    users: List[UnifiedUserResponse]
