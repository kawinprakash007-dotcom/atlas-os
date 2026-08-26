import time
from typing import Optional
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from atlas_ui.backend.schemas.admin import (
    AdminUserCreateRequest,
    AdminUserStatusUpdateRequest,
    UnifiedUserResponse,
    UnifiedUserListResponse
)
from atlas_ui.backend.identity.risk_calculator import RiskCalculator

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

@router.post("/users", response_model=UnifiedUserResponse)
async def create_user(body: AdminUserCreateRequest, request: Request):
    access_controller = request.app.state.access_controller
    account_registry = request.app.state.account_registry
    credential_verifier = request.app.state.credential_verifier
    person_registry = request.app.state.person_registry
    auth_audit = request.app.state.auth_audit
    
    # Need session to check role
    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")
        
    session_manager = request.app.state.session_manager
    sess = session_manager.validate_session(sess_id) if sess_id else None
    
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
        
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    import secrets
    try:
        user_salt = secrets.token_hex(16)
        user_hash = credential_verifier.hash_password(body.password, bytes.fromhex(user_salt)).hex()
        
        acc = account_registry.create_account(
            username=body.username,
            password_hash=user_hash,
            password_salt=user_salt,
            role=body.role,
            enabled=body.enabled
        )
        
        person = person_registry.create_person(
            display_name=body.display_name,
            account_id=acc.account_id,
            role=body.role
        )
        
        auth_audit.log_attempt(
            event_type="USER_CREATED",
            account_id=sess.account_id,
            role=sess.role,
            access_result="SUCCESS",
            person_id=person.atlas_person_id,
            username=acc.username,
            ip_address=request.client.host if request.client else None,
            device_info=request.headers.get("user-agent"),
            metadata={"new_account_id": acc.account_id, "new_role": acc.role},
        )
        
        return UnifiedUserResponse(
            account_id=acc.account_id,
            username=acc.username,
            role=acc.role,
            enabled=acc.enabled,
            atlas_person_id=person.atlas_person_id,
            display_name=person.display_name,
            created_at=person.created_at,
            last_updated=person.updated_at,
            face_enrollment_status=person.face_enrollment_status,
            enrolled_at=person.enrolled_at,
            template_count=person.template_count,
            last_biometric_verification=person.last_biometric_verification,
            last_verification_status=person.last_verification_status,
            first_login=person.first_login,
            last_login=person.last_login,
            login_count=person.login_count,
            current_session_status="OFFLINE",
            current_session_id=None,
            last_logout=person.last_logout,
            total_session_duration=person.total_session_duration,
            last_activity=None,
            active_sessions=0,
            online=False,
            last_access_timestamp=person.last_access_timestamp,
            last_access_ip=person.last_access_ip,
            last_access_device=person.last_access_device,
            gps_latitude=person.gps_latitude,
            gps_longitude=person.gps_longitude,
            gps_accuracy=person.gps_accuracy,
            location_permission=person.location_permission,
            latest_verification_snapshot=person.latest_verification_snapshot,
            latest_verification_timestamp=person.latest_verification_timestamp,
            latest_verification_result=person.latest_verification_result,
            latest_verification_score=person.latest_verification_score,
            failed_login_attempts=person.failed_login_attempts,
            last_failed_login=person.last_failed_login,
            account_lock_status=person.account_lock_status,
            recent_security_events=person.recent_security_events,
        )
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/users/{account_id}/status")
async def update_user_status(account_id: str, body: AdminUserStatusUpdateRequest, request: Request):
    access_controller = request.app.state.access_controller
    account_registry = request.app.state.account_registry
    auth_audit = request.app.state.auth_audit
    
    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")
        
    session_manager = request.app.state.session_manager
    sess = session_manager.validate_session(sess_id) if sess_id else None
    
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
        
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    try:
        acc = account_registry.get_account(account_id)
        if not acc:
            return JSONResponse(status_code=404, content={"error": "Account not found"})
            
        if body.enabled:
            account_registry.update_account(account_id, enabled=True)
            event_type = "USER_ENABLED"
        else:
            account_registry.update_account(account_id, enabled=False)
            event_type = "USER_DISABLED"
            # Revoke all sessions for this account
            active_sessions = session_manager.list_active_sessions()
            for s in active_sessions:
                if s.account_id == account_id:
                    session_manager.revoke_session(s.session_id)
                    
        # Resolve target person for enriched logging
        person_registry = request.app.state.person_registry
        target_person = person_registry.get_person_by_account(account_id)
        target_username = acc.username

        auth_audit.log_attempt(
            event_type="ACCOUNT_ENABLED" if body.enabled else "ACCOUNT_DISABLED",
            account_id=sess.account_id,
            role=sess.role,
            access_result="SUCCESS",
            person_id=target_person.atlas_person_id if target_person else None,
            username=target_username,
            ip_address=request.client.host if request.client else None,
            device_info=request.headers.get("user-agent"),
            metadata={"target_account_id": account_id, "enabled": body.enabled},
        )
        
        return {"success": True, "message": f"Account status updated to {'enabled' if body.enabled else 'disabled'}"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.get("/users", response_model=UnifiedUserListResponse)
async def list_users(request: Request):
    access_controller = request.app.state.access_controller
    account_registry = request.app.state.account_registry
    person_registry = request.app.state.person_registry
    session_manager = request.app.state.session_manager
    
    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")
        
    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "VIEW_SYSTEM"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    users = []
    active_sessions = session_manager.list_active_sessions()
    auth_audit = getattr(request.app.state, "auth_audit", None)
    
    for acc in account_registry.list_accounts():
        person = person_registry.get_person_by_account(acc.account_id)
        
        # Risk Calculation
        risk_level = "LOW"
        risk_reasons = ["No recent failures"]
        if auth_audit and person:
            user_audit_records = auth_audit.filter_records(account_id=acc.account_id)
            person_audit_records = auth_audit.filter_records(person_id=person.atlas_person_id)
            seen = set([r.attempt_id for r in user_audit_records])
            for r in person_audit_records:
                if r.attempt_id not in seen:
                    user_audit_records.append(r)
            
            risk = RiskCalculator.calculate_risk(person, user_audit_records)
            risk_level = risk["level"]
            risk_reasons = risk["reasons"]
        
        # Session stats for this account
        acc_sessions = [s for s in active_sessions if s.account_id == acc.account_id]
        online = len(acc_sessions) > 0
        last_activity = max([s.last_activity for s in acc_sessions]) if acc_sessions else None
        last_login_sess = max([s.created_at for s in acc_sessions]) if acc_sessions else None
        current_session_id = acc_sessions[0].session_id if acc_sessions else None
        current_session_status = "ONLINE" if online else "OFFLINE"

        users.append(UnifiedUserResponse(
            account_id=acc.account_id,
            username=acc.username,
            role=acc.role,
            enabled=acc.enabled,
            atlas_person_id=person.atlas_person_id if person else None,
            display_name=person.display_name if person else None,
            created_at=person.created_at if person else None,
            last_updated=person.updated_at if person else None,
            # Biometric
            face_enrollment_status=person.face_enrollment_status if person else "NOT_ENROLLED",
            enrolled_at=person.enrolled_at if person else None,
            template_count=person.template_count if person else 0,
            last_biometric_verification=person.last_biometric_verification if person else None,
            last_verification_status=person.last_verification_status if person else None,
            # Access activity
            first_login=person.first_login if person else None,
            last_login=person.last_login if person else last_login_sess,
            login_count=person.login_count if person else 0,
            current_session_status=current_session_status,
            current_session_id=current_session_id,
            last_logout=person.last_logout if person else None,
            total_session_duration=person.total_session_duration if person else 0.0,
            last_activity=last_activity,
            active_sessions=len(acc_sessions),
            online=online,
            # Last access info
            last_access_timestamp=person.last_access_timestamp if person else None,
            last_access_ip=person.last_access_ip if person else None,
            last_access_device=person.last_access_device if person else None,
            gps_latitude=person.gps_latitude if person else None,
            gps_longitude=person.gps_longitude if person else None,
            gps_accuracy=person.gps_accuracy if person else None,
            location_permission=person.location_permission if person else None,
            # Verification evidence
            latest_verification_snapshot=person.latest_verification_snapshot if person else None,
            latest_verification_timestamp=person.latest_verification_timestamp if person else None,
            latest_verification_result=person.latest_verification_result if person else None,
            latest_verification_score=person.latest_verification_score if person else None,
            # Security
            failed_login_attempts=person.failed_login_attempts if person else 0,
            last_failed_login=person.last_failed_login if person else None,
            account_lock_status=person.account_lock_status if person else False,
            recent_security_events=person.recent_security_events if person else [],
            risk_level=risk_level,
            risk_reasons=risk_reasons,
        ))
        
    return UnifiedUserListResponse(users=users)


@router.get("/users/{account_id}/activity")
async def get_user_activity(account_id: str, request: Request):
    access_controller = request.app.state.access_controller
    auth_audit = request.app.state.auth_audit
    session_manager = request.app.state.session_manager
    
    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")
        
    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "VIEW_SYSTEM"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    records = auth_audit.list_records()
    user_records = [r for r in records if r.account_id == account_id or r.failure_category == account_id]
    
    return {"activity": [r.__dict__ for r in user_records]}


@router.post("/sessions/{session_id}/revoke")
async def revoke_session(session_id: str, request: Request):
    access_controller = request.app.state.access_controller
    session_manager = request.app.state.session_manager
    auth_audit = request.app.state.auth_audit
    
    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")
        
    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    target_session = session_manager.get_session(session_id)
    if not target_session:
        return JSONResponse(status_code=404, content={"error": "Session not found"})
        
    session_manager.revoke_session(session_id)
    
    # Resolve target for enriched logging
    target_person_registry = request.app.state.person_registry
    target_acct_person = target_person_registry.get_person_by_account(target_session.account_id)

    auth_audit.log_attempt(
        event_type="SESSION_REVOKED",
        account_id=sess.account_id,
        role=sess.role,
        access_result="SUCCESS",
        person_id=target_acct_person.atlas_person_id if target_acct_person else None,
        session_id=session_id,
        ip_address=request.client.host if request.client else None,
        device_info=request.headers.get("user-agent"),
        metadata={"target_account_id": target_session.account_id},
    )
    
    return {"success": True, "message": "Session revoked"}


# ---------------------------------------------------------------------------
# Security Log
# ---------------------------------------------------------------------------

@router.get("/security-log")
async def get_security_log(
    request: Request,
    event_type: Optional[str] = None,
    person_id: Optional[str] = None,
    limit: int = 200,
):
    """
    Returns the enriched security/activity log.
    Requires MANAGE_USERS permission.
    Results are newest-first, capped at limit (max 500).
    Supports optional query filters: event_type, person_id.
    """
    auth_audit = request.app.state.auth_audit
    access_controller = request.app.state.access_controller
    session_manager = request.app.state.session_manager

    sess_id = request.headers.get("Authorization")
    if sess_id and sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = request.headers.get("x-session-id") or request.cookies.get("session_id")

    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    effective_limit = min(max(1, limit), 500)
    records = auth_audit.filter_records(
        event_type=event_type,
        person_id=person_id,
        limit=effective_limit,
    )

    def _serialize_record(r) -> dict:
        return {
            "event_id": r.attempt_id,
            "event_type": r.event_type,
            "timestamp": r.timestamp,
            "account_id": r.account_id,
            "person_id": r.person_id,
            "username": r.username,
            "session_id": r.session_id,
            "role": r.role,
            "access_result": r.access_result,
            "credential_verified": r.credential_verified,
            "face_verified": r.face_verified,
            "failure_category": r.failure_category,
            "ip_address": r.ip_address,
            "device_info": r.device_info,
            "gps_latitude": r.gps_latitude,
            "gps_longitude": r.gps_longitude,
            "gps_accuracy": r.gps_accuracy,
            "biometric_score": r.biometric_score,
            "verification_result": r.verification_result,
            "metadata": r.metadata,
        }

    return {
        "total": len(records),
        "limit": effective_limit,
        "events": [_serialize_record(r) for r in records],
    }


# ---------------------------------------------------------------------------
# Phase 5 — Verification Snapshot Retrieval (admin-only)
# ---------------------------------------------------------------------------

def _require_admin_session(request: Request):
    """
    Extract and validate the session from the request.

    Returns (session, None) on success.
    Returns (None, JSONResponse) with the appropriate error when auth fails.
    """
    access_controller = request.app.state.access_controller
    session_manager = request.app.state.session_manager

    sess_id = request.headers.get("Authorization", "")
    if sess_id.startswith("Bearer "):
        sess_id = sess_id[7:]
    else:
        sess_id = (
            request.headers.get("x-session-id")
            or request.cookies.get("session_id")
        )

    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return None, JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return None, JSONResponse(status_code=403, content={"error": "Forbidden: admin access required"})
    return sess, None


@router.get(
    "/snapshots/{snapshot_id}",
    summary="Retrieve a single verification snapshot by ID (admin only)",
)
async def get_verification_snapshot(snapshot_id: str, request: Request):
    """
    Returns the full VerificationSnapshot record for the given snapshot_id,
    including the thumbnail_b64 image when one was recorded.

    Access is restricted to sessions with MANAGE_USERS permission.
    Normal users cannot access this endpoint.

    Returns 404 when the snapshot_id is unknown or has been evicted from the
    in-memory ring buffer (MAX_PER_PERSON=50 entries per person).
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    snap_store = getattr(request.app.state, "snapshot_store", None)
    if snap_store is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Snapshot store not available"},
        )

    snap = snap_store.get(snapshot_id)
    if snap is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Snapshot '{snapshot_id}' not found"},
        )

    return {
        "snapshot_id":   snap.snapshot_id,
        "person_id":     snap.person_id,
        "account_id":    snap.account_id,
        "session_id":    snap.session_id,
        "timestamp":     snap.timestamp,
        "result":        snap.result,
        "score":         snap.score,
        "thumbnail_b64": snap.thumbnail_b64,
    }


@router.get(
    "/people/{person_id}/snapshots",
    summary="List verification snapshots for a person (admin only)",
)
async def list_person_snapshots(
    person_id: str,
    request: Request,
    include_image: bool = False,
):
    """
    Returns the verification snapshot history for the given person_id,
    newest-first, capped at 50 entries.

    By default thumbnail_b64 is omitted from each entry to keep the list
    response lean.  Pass ?include_image=true to include thumbnails.

    Access is restricted to sessions with MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    # Verify the person exists in the registry
    person_registry = request.app.state.person_registry
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Person '{person_id}' not found"},
        )

    snap_store = getattr(request.app.state, "snapshot_store", None)
    if snap_store is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Snapshot store not available"},
        )

    snapshots = snap_store.list_for_person(person_id, include_image=include_image)
    return {
        "person_id": person_id,
        "total":     len(snapshots),
        "snapshots": snapshots,
    }


# ---------------------------------------------------------------------------
# Phase 6 — Advanced User Information (admin-only)
# ---------------------------------------------------------------------------
# All five endpoints below require MANAGE_USERS permission and reuse the
# _require_admin_session() helper defined above.
# ---------------------------------------------------------------------------

def _paginate(items: list, page: int, limit: int) -> dict:
    """
    Generic pagination helper.  page is 1-indexed; limit is capped at 200.
    Returns a dict with pagination metadata and the sliced items list.
    """
    limit = min(max(1, limit), 200)
    page  = max(1, page)
    total = len(items)
    start = (page - 1) * limit
    end   = start + limit
    return {
        "total":        total,
        "page":         page,
        "limit":        limit,
        "total_pages":  max(1, -(-total // limit)),   # ceiling division
        "items":        items[start:end],
    }


def _serialize_audit_record(r) -> dict:
    """Serialize a single AuditRecord to a plain dict for API responses."""
    return {
        "event_id":          r.attempt_id,
        "event_type":        r.event_type,
        "timestamp":         r.timestamp,
        "account_id":        r.account_id,
        "person_id":         r.person_id,
        "session_id":        r.session_id,
        "access_result":     r.access_result,
        "credential_verified": r.credential_verified,
        "face_verified":     r.face_verified,
        "failure_category":  r.failure_category,
        "ip_address":        r.ip_address,
        "device_info":       r.device_info,
        "gps_latitude":      r.gps_latitude,
        "gps_longitude":     r.gps_longitude,
        "gps_accuracy":      r.gps_accuracy,
        "biometric_score":   r.biometric_score,
        "verification_result": r.verification_result,
        "metadata":          r.metadata,
    }


# ---------------------------------------------------------------------------
# P6-1  User List Summary
# ---------------------------------------------------------------------------

@router.get(
    "/users/summary",
    summary="Lightweight summary list of all users (admin only)",
)
async def get_user_summary_list(request: Request):
    """
    Returns a lightweight list of all registered users with key fields needed
    for an admin overview table.

    Fields per user:
        person_id, username, full_name (display_name), role, account_status,
        face_enrollment_status, online, last_login, last_access_location
        (lat/lon/accuracy only when recorded), latest_verification_result.

    Requires MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    account_registry  = request.app.state.account_registry
    person_registry   = request.app.state.person_registry
    session_manager   = request.app.state.session_manager

    active_sessions = session_manager.list_active_sessions()
    online_account_ids = {s.account_id for s in active_sessions}

    summary = []
    for acc in account_registry.list_accounts():
        person = person_registry.get_person_by_account(acc.account_id)

        # Location summary — only real recorded coordinates
        loc_summary = None
        if person and person.gps_latitude is not None and person.gps_longitude is not None:
            loc_summary = {
                "latitude":  person.gps_latitude,
                "longitude": person.gps_longitude,
                "accuracy":  person.gps_accuracy,
                "recorded_at": person.last_access_timestamp,
            }

        summary.append({
            "person_id":             person.atlas_person_id if person else None,
            "username":              acc.username,
            "full_name":             person.display_name if person else None,
            "role":                  acc.role,
            "account_status":        "ENABLED" if acc.enabled else "DISABLED",
            "biometric_enrollment":  person.face_enrollment_status if person else "NOT_ENROLLED",
            "online":                acc.account_id in online_account_ids,
            "last_login":            person.last_login if person else None,
            "last_access_location":  loc_summary,
            "latest_verification_result": (
                person.latest_verification_result if person else None
            ),
        })

    return {"total": len(summary), "users": summary}


# ---------------------------------------------------------------------------
# P6-2  Detailed User Profile
# ---------------------------------------------------------------------------

@router.get(
    "/people/{person_id}/profile",
    summary="Full detailed profile for a single user (admin only)",
)
async def get_user_profile(person_id: str, request: Request):
    """
    Returns the complete profile for a user identified by person_id.

    Includes:
        - Complete identity information (name, account, role, status)
        - Account status (enabled/disabled)
        - Biometric information & enrollment details
        - Login statistics
        - Current/last session info
        - Latest location (real GPS only)
        - Latest verification snapshot reference
        - Security state & recent security events

    Requires MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    person_registry  = request.app.state.person_registry
    account_registry = request.app.state.account_registry
    session_manager  = request.app.state.session_manager

    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Person '{person_id}' not found"},
        )

    # Account info
    acc = account_registry.get_account(person.account_id) if person.account_id else None

    # Session info — current live session for this account
    active_sessions = session_manager.list_active_sessions()
    person_sessions = [
        s for s in active_sessions if s.account_id == (person.account_id or "")
    ]
    current_session = person_sessions[0] if person_sessions else None

    # Snapshot count (best-effort — store may not be available)
    snap_store = getattr(request.app.state, "snapshot_store", None)
    snapshot_count = snap_store.person_count(person_id) if snap_store else 0

    # Location — only real recorded coordinates
    location = None
    if person.gps_latitude is not None and person.gps_longitude is not None:
        location = {
            "latitude":    person.gps_latitude,
            "longitude":   person.gps_longitude,
            "accuracy":    person.gps_accuracy,
            "permission":  person.location_permission,
            "recorded_at": person.last_access_timestamp,
        }

    # Risk Calculation
    auth_audit = getattr(request.app.state, "auth_audit", None)
    risk_level = "LOW"
    risk_reasons = ["No recent failures"]
    if auth_audit and person:
        user_audit_records = auth_audit.filter_records(account_id=acc.account_id if acc else None)
        person_audit_records = auth_audit.filter_records(person_id=person.atlas_person_id)
        seen = set([r.attempt_id for r in user_audit_records])
        for r in person_audit_records:
            if r.attempt_id not in seen:
                user_audit_records.append(r)
        
        risk = RiskCalculator.calculate_risk(person, user_audit_records)
        risk_level = risk["level"]
        risk_reasons = risk["reasons"]

    return {
        # ── Identity
        "person_id":        person.atlas_person_id,
        "display_name":     person.display_name,
        "role":             person.role,
        "status":           person.status,
        "created_at":       person.created_at,
        "updated_at":       person.updated_at,
        # ── Account
        "account_id":       acc.account_id if acc else person.account_id,
        "username":         acc.username if acc else None,
        "account_enabled":  acc.enabled if acc else None,
        # ── Biometric
        "face_enrollment_status":         person.face_enrollment_status,
        "enrolled_at":                    person.enrolled_at,
        "template_count":                 person.template_count,
        "last_biometric_verification":    person.last_biometric_verification,
        "last_verification_status":       person.last_verification_status,
        "latest_verification_result":     person.latest_verification_result,
        "latest_verification_score":      person.latest_verification_score,
        "latest_verification_timestamp":  person.latest_verification_timestamp,
        "snapshot_count":                 snapshot_count,
        # thumbnail excluded from profile — use snapshot endpoint for images
        "has_latest_snapshot": person.latest_verification_snapshot is not None,
        # ── Login Statistics
        "first_login":             person.first_login,
        "last_login":              person.last_login,
        "login_count":             person.login_count,
        "last_logout":             person.last_logout,
        "total_session_duration":  person.total_session_duration,
        # ── Current Session
        "online":              current_session is not None,
        "current_session_id":  current_session.session_id if current_session else None,
        "session_started_at":  current_session.created_at if current_session else None,
        "session_expires_at":  current_session.expires_at if current_session else None,
        "session_last_activity": current_session.last_activity if current_session else None,
        # ── Location
        "last_access_ip":     person.last_access_ip,
        "last_access_device": person.last_access_device,
        "last_access_location": location,
        "location_permission": person.location_permission,
        # ── Security
        "failed_login_attempts": person.failed_login_attempts,
        "last_failed_login":     person.last_failed_login,
        "account_lock_status":   person.account_lock_status,
        "recent_security_events": person.recent_security_events[-10:],  # last 10 only
        # ── Risk
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
    }


# ---------------------------------------------------------------------------
# P6-3  User Activity History (paginated)
# ---------------------------------------------------------------------------

@router.get(
    "/people/{person_id}/activity",
    summary="Paginated audit-event history for a user (admin only)",
)
async def get_user_activity_history(
    person_id: str,
    request: Request,
    page: int = 1,
    limit: int = 50,
    event_type: Optional[str] = None,
):
    """
    Returns a paginated list of audit events for the given person_id,
    newest-first.

    Query params:
        page       — 1-indexed page number (default: 1)
        limit      — events per page, max 200 (default: 50)
        event_type — optional filter (e.g. LOGIN_SUCCESS, BIOMETRIC_VERIFICATION_SUCCESS)

    Each event includes: event_type, timestamp, access_result, ip_address,
    device_info, gps coordinates (when recorded), biometric_score,
    verification_result, failure_category.

    Requires MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    person_registry = request.app.state.person_registry
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Person '{person_id}' not found"},
        )

    auth_audit = request.app.state.auth_audit
    # filter_records returns newest-first, capped at 500
    raw_records = auth_audit.filter_records(
        person_id=person_id,
        event_type=event_type if event_type else None,
        limit=500,
    )

    serialized = [_serialize_audit_record(r) for r in raw_records]
    paged = _paginate(serialized, page, limit)
    return {
        "person_id":   person_id,
        "event_type":  event_type,
        **paged,
    }


# ---------------------------------------------------------------------------
# P6-4  User Session History (paginated)
# ---------------------------------------------------------------------------

@router.get(
    "/people/{person_id}/sessions",
    summary="Paginated session history for a user (admin only)",
)
async def get_user_session_history(
    person_id: str,
    request: Request,
    page: int = 1,
    limit: int = 50,
):
    """
    Returns a paginated list of completed and current sessions for the given
    person_id, newest-first.

    Session history is reconstructed from LOGIN_SUCCESS and LOGOUT audit
    records because the SessionManager only keeps live sessions in memory
    (completed sessions are not persisted).  Each entry pairs a login event
    with a matching logout where available.

    Fields per session:
        session_id, login_time, logout_time, duration_seconds (null if active),
        session_status (ACTIVE | COMPLETED | UNKNOWN), login_ip, login_device,
        login_location (lat/lon when recorded), verification_status.

    Requires MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    person_registry = request.app.state.person_registry
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Person '{person_id}' not found"},
        )

    auth_audit = request.app.state.auth_audit

    # Collect LOGIN_SUCCESS events for this person
    login_events = auth_audit.filter_records(
        person_id=person_id,
        event_type="LOGIN_SUCCESS",
        limit=500,
    )
    # Collect LOGOUT events for this person
    logout_events = auth_audit.filter_records(
        person_id=person_id,
        event_type="LOGOUT",
        limit=500,
    )

    # Build lookup: session_id → logout record
    logout_by_session: dict = {}
    for ev in logout_events:
        if ev.session_id:
            logout_by_session[ev.session_id] = ev

    # Check which sessions are currently live
    session_manager = request.app.state.session_manager
    active_session_ids = {s.session_id for s in session_manager.list_active_sessions()}

    sessions = []
    for login_ev in login_events:
        sid = login_ev.session_id
        logout_ev = logout_by_session.get(sid) if sid else None

        login_time  = login_ev.timestamp
        logout_time = logout_ev.timestamp if logout_ev else None
        duration    = (logout_time - login_time) if logout_time else None
        is_active   = sid in active_session_ids if sid else False

        # Location at login — only real coordinates
        loc = None
        if login_ev.gps_latitude is not None and login_ev.gps_longitude is not None:
            loc = {
                "latitude":  login_ev.gps_latitude,
                "longitude": login_ev.gps_longitude,
                "accuracy":  login_ev.gps_accuracy,
            }

        sessions.append({
            "session_id":        sid,
            "login_time":        login_time,
            "logout_time":       logout_time,
            "duration_seconds":  round(duration, 2) if duration is not None else None,
            "session_status":    "ACTIVE" if is_active else ("COMPLETED" if logout_ev else "UNKNOWN"),
            "login_ip":          login_ev.ip_address,
            "login_device":      login_ev.device_info,
            "login_location":    loc,
            "verification_status": login_ev.verification_result,
            "face_verified":     login_ev.face_verified,
        })

    paged = _paginate(sessions, page, limit)
    return {"person_id": person_id, **paged}


# ---------------------------------------------------------------------------
# P6-5  User Location History (paginated, real locations only)
# ---------------------------------------------------------------------------

@router.get(
    "/people/{person_id}/locations",
    summary="Real recorded location history for a user (admin only)",
)
async def get_user_location_history(
    person_id: str,
    request: Request,
    page: int = 1,
    limit: int = 100,
):
    """
    Returns a paginated list of real GPS coordinates recorded for the user,
    extracted from audit event records, newest-first.

    IMPORTANT: Only events where gps_latitude AND gps_longitude are non-null
    are included.  No addresses or coordinates are fabricated.

    Fields per entry:
        timestamp, event_type, latitude, longitude, accuracy (metres),
        ip_address, device_info.

    Requires MANAGE_USERS permission.
    """
    sess, err = _require_admin_session(request)
    if err is not None:
        return err

    person_registry = request.app.state.person_registry
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Person '{person_id}' not found"},
        )

    auth_audit = request.app.state.auth_audit
    all_records = auth_audit.filter_records(person_id=person_id, limit=500)

    # Keep only records with real GPS coordinates
    locations = []
    for r in all_records:
        if r.gps_latitude is None or r.gps_longitude is None:
            continue
        locations.append({
            "timestamp":   r.timestamp,
            "event_type":  r.event_type,
            "latitude":    r.gps_latitude,
            "longitude":   r.gps_longitude,
            "accuracy":    r.gps_accuracy,
            "ip_address":  r.ip_address,
            "device_info": r.device_info,
        })

    paged = _paginate(locations, page, limit)
    return {"person_id": person_id, **paged}
