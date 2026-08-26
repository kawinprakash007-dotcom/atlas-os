import os
import dataclasses
import traceback
from typing import Any, Optional
from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from atlas_ui.backend.configuration import UIConfiguration
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.identity.person_models import Person
from atlas_ui.backend.identity.person_registry import PersonRegistry
from atlas_ui.backend.authorization.access_controller import AccessController
from atlas_ui.backend.sessions.session_manager import SessionManager
from atlas_ui.backend.audit.auth_audit import AuthenticationAudit
from atlas_ui.backend.services.authentication_service import AuthenticationService
from atlas_ui.backend.services.dashboard_service import DashboardService
from atlas_ui.backend.schemas.auth import LoginRequest, LoginResponse
from atlas_ui.backend.schemas.dashboard import DashboardDataResponse
from atlas_ui.backend.schemas.identity import (
    PersonCreateRequest, PersonResponse
)
from atlas_ui.backend.routes.biometric import router as biometric_router
from atlas_ui.backend.vision.verification_snapshot_store import VerificationSnapshotStore




app = FastAPI(title="ATLAS OS User Interface API", version="1.9.0")

# Setup Shared Composition Root Instances
config = UIConfiguration()
account_registry = AccountRegistry()
credential_verifier = CredentialVerifier(account_registry)
person_registry = PersonRegistry()

access_controller = AccessController()
session_manager = SessionManager(default_lifetime_seconds=config.session_lifetime_seconds)
auth_audit = AuthenticationAudit()

auth_service = AuthenticationService(
    account_registry=account_registry,
    credential_verifier=credential_verifier,
    person_registry=person_registry,
    session_manager=session_manager,
    audit=auth_audit
)

dashboard_service = DashboardService()

from pathlib import Path
print("==================================================", flush=True)
print("[MAIN] Composition Root Initialization (Non-Biometric Baseline):", flush=True)
print(f"[MAIN] Path(__file__).resolve(): {Path(__file__).resolve()}", flush=True)
print(f"[MAIN] Path.cwd(): {Path.cwd()}", flush=True)
print(f"[MAIN] auth_service: type={type(auth_service)}", flush=True)
print(f"[MAIN] auth_service: type={type(auth_service)}", flush=True)
print("==================================================", flush=True)

# Inject dependencies on app state for access across handlers
app.state.account_registry = account_registry
app.state.credential_verifier = credential_verifier
app.state.person_registry = person_registry
app.state.access_controller = access_controller
app.state.session_manager = session_manager
app.state.auth_audit = auth_audit
app.state.auth_service = auth_service
app.state.dashboard_service = dashboard_service

# Phase 5: Verification snapshot store (in-memory, capped per-person ring buffer)
snapshot_store = VerificationSnapshotStore()
app.state.snapshot_store = snapshot_store

# Seed default mock accounts safely
def seed_mock_accounts():
    import secrets
    
    # 1. ADMIN USER
    admin_salt = secrets.token_hex(16)
    admin_hash = credential_verifier.hash_password("admin_pass_123", bytes.fromhex(admin_salt)).hex()
    admin_acc = account_registry.create_account(
        username="admin_user",
        password_hash=admin_hash,
        password_salt=admin_salt,
        role="ADMIN"
    )
    # Create matching ADMIN Person
    admin_person = person_registry.create_person(
        display_name="Admin User",
        account_id=admin_acc.account_id,
        role="ADMIN",
        atlas_person_id="ATLAS-P-88888888"
    )
    
    # 2. USER USER
    user_salt = secrets.token_hex(16)
    user_hash = credential_verifier.hash_password("user_pass_123", bytes.fromhex(user_salt)).hex()
    user_acc = account_registry.create_account(
        username="normal_user",
        password_hash=user_hash,
        password_salt=user_salt,
        role="USER"
    )
    # Create matching USER Person
    user_person = person_registry.create_person(
        display_name="Normal User",
        account_id=user_acc.account_id,
        role="USER",
        atlas_person_id="ATLAS-P-11111111"
    )

    # Sync enrollment statuses from FaceTemplateStore
    from atlas_ui.backend.routes.biometric import _face_store
    for p in [admin_person, user_person]:
        if _face_store.has_templates(p.atlas_person_id):
            person_registry.update_person(p.atlas_person_id, face_enrollment_status="ENROLLED")

seed_mock_accounts()


# Helper to convert dataclasses to serializable dicts
def make_serializable(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        result = {}
        for f in dataclasses.fields(obj):
            val = getattr(obj, f.name)
            result[f.name] = make_serializable(val)
        return result
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [make_serializable(item) for item in obj]
    else:
        return obj


# Helper to extract session ID from request headers
def get_session_id_from_request(request: Request) -> Optional[str]:
    # 1. Check Authorization header: Bearer <session_id>
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        parts = auth_header.split(" ")
        if len(parts) == 2:
            return parts[1]
    # 2. Check Custom header: X-Session-ID
    x_sess = request.headers.get("x-session-id")
    if x_sess:
        return x_sess
    # 3. Check Cookie
    cookie_sess = request.cookies.get("session_id")
    if cookie_sess:
        return cookie_sess
    return None


def get_current_session(request: Request):
    sess_id = get_session_id_from_request(request)
    if not sess_id:
        return None
    return session_manager.validate_session(sess_id)


# --- HTTP APIs ---

@app.post("/api/v1/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    # Extract optional GPS fields — None when the client did not send them
    _gps = body.gps_location
    res = auth_service.login(
        username=body.username,
        password=body.password,
        biometric_input=body.biometric_input,
        ip_address=ip_address,
        user_agent=user_agent,
        gps_latitude=_gps.latitude if _gps else None,
        gps_longitude=_gps.longitude if _gps else None,
        gps_accuracy=_gps.accuracy if _gps else None,
        location_permission=_gps.status if _gps else None,
    )
    if not res["authenticated"]:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content=res
        )
    return res


@app.post("/api/v1/auth/logout")
async def logout(request: Request):
    sess_id = get_session_id_from_request(request)
    if sess_id:
        auth_service.logout(sess_id)
    return {"message": "Logged out successfully"}


@app.get("/api/v1/auth/session")
async def get_session(request: Request):
    sess_id = get_session_id_from_request(request)
    if not sess_id:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"authenticated": False, "message": "No active session."}
        )
        
    sess = session_manager.validate_session(sess_id)
    if not sess:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"authenticated": False, "message": "Session invalid or expired."}
        )
        
    return make_serializable(sess)


@app.get("/api/v1/dashboard", response_model=DashboardDataResponse)
async def get_dashboard(request: Request):
    sess_id = get_session_id_from_request(request)
    if not sess_id:
        auth_audit.log_attempt(
            event_type="ACCESS_DENIED",
            access_result="FAILURE",
            failure_category="EXPIRED_SESSION"
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Access denied. Active session required."}
        )

    sess = session_manager.validate_session(sess_id)
    if not sess:
        auth_audit.log_attempt(
            event_type="ACCESS_DENIED",
            access_result="FAILURE",
            failure_category="EXPIRED_SESSION"
        )
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Session has expired."}
        )

    # Resolve roles and verify permissions
    # User dashboard views require VIEW_SYSTEM permission
    if not access_controller.has_permission(sess.role, "VIEW_SYSTEM"):
        auth_audit.log_attempt(
            event_type="ACCESS_DENIED",
            account_id=sess.account_id,
            access_result="FAILURE",
            role=sess.role,
            failure_category="ACCESS_DENIED"
        )
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"error": "Access denied. Insufficient permissions."}
        )

    # Fetch role appropriate data
    data = dashboard_service.get_dashboard_data(sess.role)
    
    # Inject person_id for biometric enrollment component
    person = person_registry.get_person_by_account(sess.account_id)
    if person:
        data["person_id"] = person.atlas_person_id
        
    return make_serializable(data)


# --- OS Identity API Routing ---

@app.post("/api/v1/people", response_model=PersonResponse)
async def create_person(body: PersonCreateRequest, request: Request):
    sess = get_current_session(request)
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "MANAGE_USERS"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    try:
        person = person_registry.create_person(
            display_name=body.display_name,
            account_id=body.account_id,
            role=body.role,
            metadata=body.metadata
        )
        return make_serializable(person)
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.get("/api/v1/people")
async def list_people(request: Request):
    sess = get_current_session(request)
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "VIEW_SYSTEM"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    people = person_registry.list_people()
    return make_serializable(people)


@app.get("/api/v1/people/{atlas_person_id}", response_model=PersonResponse)
async def get_person(atlas_person_id: str, request: Request):
    sess = get_current_session(request)
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    if not access_controller.has_permission(sess.role, "VIEW_SYSTEM"):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})

    person = person_registry.get_person(atlas_person_id)
    if not person:
        return JSONResponse(status_code=404, content={"error": "Person not found"})
    return make_serializable(person)





# --- Admin APIs ---
from atlas_ui.backend.routes.admin import router as admin_router
app.include_router(admin_router)

# --- Serve Frontend SPA ---

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

# Mount Static assets
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>ATLAS OS Frontend Files Missing</h1>")


# --- Phase 4A: Biometric API ---
app.include_router(biometric_router)

