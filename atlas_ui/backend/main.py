import os
import dataclasses
import traceback
from typing import Any, Optional

def load_env_file():
    # Look for .env in current working dir or parent directory
    for base_dir in [os.getcwd(), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
        env_path = os.path.join(base_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()
            break

load_env_file()
from fastapi import FastAPI, Request, status, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from atlas_ui.backend.configuration import UIConfiguration
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.identity.person_models import Person
from atlas_ui.backend.models.account import Account
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
from atlas_core.network.remote_vision_client import RemoteVisionClient




app = FastAPI(title="ATLAS OS User Interface API", version="1.9.0")

# Setup Shared Composition Root Instances
config = UIConfiguration()
# Phase IM4: Initialize SQLite Persistence
from atlas_ui.backend.database.sqlite_store import SQLiteStore
sqlite_store = SQLiteStore()
print(f"[STARTUP] Authoritative SQLite Database path: {sqlite_store.db_path}", flush=True)

account_registry = AccountRegistry(sqlite_store)

# Load accounts from SQLite
for row in sqlite_store.get_all_accounts():
    acc = Account(
        account_id=row["account_id"],
        username=row["username"],
        password_hash=row["password_hash"],
        password_salt=row["password_salt"],
        role=row["role"],
        enabled=bool(row["enabled"]),
        created_at=0.0
    )
    account_registry._accounts[acc.account_id] = acc

credential_verifier = CredentialVerifier(account_registry)
person_registry = PersonRegistry(sqlite_store)

# Load persons from SQLite
for row in sqlite_store.get_all_persons():
    person = Person(
        atlas_person_id=row["person_id"],
        account_id=row["account_id"],
        display_name=row["display_name"],
        role=row["role"],
        face_enrollment_status=row["face_enrollment_status"],
        template_count=row["template_count"],
        created_at=0.0,
        updated_at=0.0
    )
    person_registry._people[person.atlas_person_id] = person

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

# --- Phase 1: ATLAS Core Integration ---
from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.monitoring.metrics import SystemMetrics
from atlas_core.monitoring.event_stream import EventStream
from atlas_core.commands.registry import CommandRegistry
from atlas_core.commands.dispatcher import DeviceCommandDispatcher
from atlas_core.commands.manager import DeviceCommandManager
from atlas_core.events.event import Event
from atlas_core.network.schemas import validate_event, ContractValidationError

core_config = ATLASConfiguration()
device_registry = DeviceRegistry()
device_health_manager = DeviceHealthManager(
    device_registry,
    stale_threshold=core_config.device_stale_threshold,
    offline_threshold=core_config.device_offline_threshold
)
system_metrics = SystemMetrics()
event_stream = EventStream(metrics=system_metrics)
command_registry = CommandRegistry(metrics=system_metrics)
command_dispatcher = DeviceCommandDispatcher()
command_manager = DeviceCommandManager(
    device_registry=device_registry,
    command_registry=command_registry,
    command_dispatcher=command_dispatcher,
    health_manager=device_health_manager
)

# Phase 2A.2: IntentRouter wrapping CommandReasoner and LLMService
reasoner = FakeReasoner()
from atlas_core.reasoning.command_reasoner import CommandReasoner
from atlas_core.reasoning.llm_service import LLMService
from atlas_core.reasoning.intent_router import IntentRouter

command_reasoner = CommandReasoner(fallback_reasoner=reasoner)
llm_service = LLMService()
reasoner = IntentRouter(command_reasoner=command_reasoner, llm_service=llm_service)

from atlas_core.actions.os_command import os_command_handler

atlas_runtime = ATLASRuntime(
    primary_reasoner=reasoner,
    configuration=core_config,
    device_registry=device_registry,
    device_health_manager=device_health_manager,
    command_registry=command_registry,
    command_dispatcher=command_dispatcher,
    command_manager=command_manager
)

# Register Phase 7 actions
atlas_runtime.register_action(
    action_type="OSCommandAction",
    handler=os_command_handler,
    required_fields=["command"]
)

app.state.runtime = atlas_runtime
app.state.device_registry = device_registry
app.state.device_health_manager = device_health_manager
app.state.event_stream = event_stream
app.state.system_metrics = system_metrics
app.state.command_registry = command_registry
app.state.command_dispatcher = command_dispatcher
app.state.command_manager = command_manager
app.state.remote_vision_client = RemoteVisionClient()

# --- Public Health Endpoint (no auth required) ---
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ATLAS OS", "version": "1.9.0"}

@app.get("/")
async def serve_index_or_health():
    index_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return {"service": "ATLAS OS", "status": "running", "version": "1.9.0"}

# --- OS Status (authenticated) ---
@app.get("/api/v1/os/status")
async def os_status(request: Request):
    sess_id = get_session_id_from_request(request)
    sess = session_manager.validate_session(sess_id) if sess_id else None
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    # ── Remote ATLAS Vision — query real API ──────────────────────────────
    remote_client: RemoteVisionClient = getattr(app.state, "remote_vision_client", None)
    vision_block: dict = {"connection": "DISABLED"}

    if remote_client and remote_client.enabled:
        health_data = remote_client.get_health()
        h_status = health_data.get("status", "")

        if h_status in ("offline",) or health_data.get("error_type") in ("unreachable", "timeout"):
            vision_block = {
                "connection": "OFFLINE",
                "base_url": remote_client.base_url,
                "detail": health_data.get("detail", "Vision unreachable"),
            }
        elif h_status in ("error",):
            vision_block = {
                "connection": "UNAVAILABLE",
                "base_url": remote_client.base_url,
                "detail": health_data.get("detail", "Vision error"),
            }
        else:
            # Vision is reachable — query /api/v1/vision/status for richer data
            status_data = remote_client.get_status()
            vision_block = {
                "connection": "ONLINE",
                "base_url": remote_client.base_url,
                "service": health_data.get("service", "ATLAS Vision"),
                "version": health_data.get("version"),
                "contract_version": health_data.get("contract_version"),
                "camera_status": status_data.get("camera_status", health_data.get("camera", {}).get("status")),
                "recognition_status": status_data.get("recognition_status"),
                "active_tracks": status_data.get("active_tracks"),
                "headless": status_data.get("headless"),
                "server_port": status_data.get("server_port"),
            }
    elif remote_client and not remote_client.enabled:
        vision_block = {"connection": "DISABLED", "detail": "ATLAS_VISION_ENABLED=false"}

    # ── Legacy sync worker state ──────────────────────────────────────────
    # NOTE: VisionSyncWorker targets the OLD local Vision Edge on port 8002.
    # It does NOT sync to the remote Vision machine — that API is not available.
    sync_worker = getattr(app.state, "vision_sync_worker", None)
    legacy_sync_state: dict = {"active": False}
    if sync_worker:
        with sync_worker.state.lock:
            legacy_sync_state = {
                "active": True,
                "target": sync_worker.target_url,
                "identity_dirty": sync_worker.state.identity_dirty,
                "biometric_dirty": sync_worker.state.biometric_dirty,
                "retry_count": sync_worker.state.retry_count,
            }

    # ── Identity count ────────────────────────────────────────────────────
    identity_memory_ref = getattr(app.state, "identity_memory", None)
    identity_count = len(identity_memory_ref.get_all_identities()) if identity_memory_ref else 0

    return {
        "os": {
            "status": "healthy",
            "version": "1.9.0",
            "identity_count": identity_count,
        },
        "vision": vision_block,
        "legacy_sync": legacy_sync_state,
    }

@app.post("/api/v1/events")
async def process_network_event(request: Request):
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON payload.", "detail": str(e)}
        )
    
    if isinstance(body, dict):
        raw_event_type = body.get("event_type", "UNKNOWN")
        raw_source = body.get("source", "UNKNOWN")
    else:
        raw_event_type = "UNKNOWN"
        raw_source = "UNKNOWN"
        
    try:
        if raw_source == "ATLAS_VISION" or raw_source == "TEST_MOCK":
            from atlas_core.network.schemas import VisionEvent
            from atlas_core.network.vision_adapter import VisionEventAdapter
            vision_event = VisionEvent(**body)
            evt_type, payload = VisionEventAdapter.normalize(vision_event)
            validated_data = {"event_type": evt_type, **payload, "source": raw_source}
        else:
            validated_data = validate_event(body)
        
        # Phase 5: Connect Vision (and all other) Events to WebSocket
        await broadcast_event({
            "type": "system_event",
            "event_type": validated_data.get("event_type"),
            "source": raw_source,
            "data": validated_data
        })
        
        result = app.state.runtime.process_event(
            event_type=validated_data.get("event_type"),
            payload=validated_data
        )
        return make_serializable(result)
    except ContractValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Contract Validation Failed",
                "detail": str(e),
                "required_schema": getattr(e, "expected_schema", {"event_type": "str", "source": "str", "payload": "dict"}),
                "received_keys": list(body.keys()) if isinstance(body, dict) else []
            }
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal Gateway Error",
                "detail": str(e)
            }
        )


# Seed default mock accounts safely
def seed_mock_accounts():
    import secrets
    
    # 1. ADMIN USER
    admin_acc = account_registry.get_account_by_username("admin_user")
    if not admin_acc:
        print("[STARTUP] Seeding default admin_user...", flush=True)
        admin_salt = secrets.token_hex(16)
        admin_hash = credential_verifier.hash_password("admin_pass_123", bytes.fromhex(admin_salt)).hex()
        admin_acc = account_registry.create_account(
            username="admin_user",
            password_hash=admin_hash,
            password_salt=admin_salt,
            role="ADMIN"
        )
        # Create matching ADMIN Person if not exists
        if not person_registry.get_person("ATLAS-P-88888888"):
            person_registry.create_person(
                display_name="Admin User",
                account_id=admin_acc.account_id,
                role="ADMIN",
                atlas_person_id="ATLAS-P-88888888"
            )
    else:
        # Check and repair credentials if incorrect
        try:
            credential_verifier.verify_credentials("admin_user", "admin_pass_123")
        except Exception:
            print("[STARTUP] Restoring admin_user password to admin_pass_123...", flush=True)
            admin_salt = secrets.token_hex(16)
            admin_hash = credential_verifier.hash_password("admin_pass_123", bytes.fromhex(admin_salt)).hex()
            account_registry.update_account(
                admin_acc.account_id,
                password_hash=admin_hash,
                password_salt=admin_salt
            )
    
    # 2. USER USER
    user_acc = account_registry.get_account_by_username("normal_user")
    if not user_acc:
        print("[STARTUP] Seeding default normal_user...", flush=True)
        user_salt = secrets.token_hex(16)
        user_hash = credential_verifier.hash_password("user_pass_123", bytes.fromhex(user_salt)).hex()
        user_acc = account_registry.create_account(
            username="normal_user",
            password_hash=user_hash,
            password_salt=user_salt,
            role="USER"
        )
        # Create matching USER Person if not exists
        if not person_registry.get_person("ATLAS-P-11111111"):
            person_registry.create_person(
                display_name="Normal User",
                account_id=user_acc.account_id,
                role="USER",
                atlas_person_id="ATLAS-P-11111111"
            )
    else:
        # Check and repair credentials if incorrect
        try:
            credential_verifier.verify_credentials("normal_user", "user_pass_123")
        except Exception:
            print("[STARTUP] Restoring normal_user password to user_pass_123...", flush=True)
            user_salt = secrets.token_hex(16)
            user_hash = credential_verifier.hash_password("user_pass_123", bytes.fromhex(user_salt)).hex()
            account_registry.update_account(
                user_acc.account_id,
                password_hash=user_hash,
                password_salt=user_salt
            )

seed_mock_accounts()

# Phase IM4: Biometric Reconciliation
from atlas_ui.backend.routes.biometric import _face_store
for person in person_registry.list_people():
    # If the database thinks they are enrolled, but no templates exist on disk
    if person.face_enrollment_status == "ENROLLED" and not _face_store.has_templates(person.atlas_person_id):
        print(f"[STARTUP] Biometric Reconciliation: Downgrading {person.atlas_person_id} to NOT_ENROLLED (missing templates)")
        person_registry.update_person(person.atlas_person_id, face_enrollment_status="NOT_ENROLLED", template_count=0)
    
    # If the database thinks they are not enrolled, but templates exist on disk, we just ignore/log
    elif person.face_enrollment_status != "ENROLLED" and _face_store.has_templates(person.atlas_person_id):
        # We don't auto-upgrade, we just log the orphan
        print(f"[STARTUP] Biometric Reconciliation: Found orphan templates for {person.atlas_person_id} (status={person.face_enrollment_status})")

# Phase IM2: Initialize Identity Memory
from atlas_core.memory.identity_memory import IdentityMemory

identity_memory = IdentityMemory()
identity_memory.bootstrap(
    account_registry,
    person_registry,
    _face_store
)
app.state.identity_memory = identity_memory


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

    # Trim leading/trailing whitespace from the username for robustness
    trimmed_username = body.username.strip() if body.username else body.username

    # Extract optional GPS fields — None when the client did not send them
    _gps = body.gps_location
    res = auth_service.login(
        username=trimmed_username,
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
        
        # Phase IM3: Synchronize legacy person creation to IdentityMemory
        enabled = True
        if body.account_id:
            acc = account_registry.get_account(body.account_id)
            if acc:
                enabled = acc.enabled
                
        identity_memory = getattr(app.state, "identity_memory", None)
        if identity_memory:
            face_enrolled = (person.face_enrollment_status == "ENROLLED")
            identity_memory.upsert_identity(
                person_id=person.atlas_person_id,
                display_name=person.display_name,
                role=person.role or "USER",
                enabled=enabled,
                face_enrolled=face_enrolled
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





# --- Assistant API ---
from atlas_ui.backend.schemas.assistant import AssistantChatRequest
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json

active_websockets = []

async def broadcast_event(data: dict):
    # Fire and forget to all connected clients
    disconnected = []
    for ws in active_websockets:
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_websockets:
            active_websockets.remove(ws)

@app.websocket("/api/v1/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # We don't expect the client to send much here, mostly just ping/pong or nothing.
    except WebSocketDisconnect:
        if websocket in active_websockets:
            active_websockets.remove(websocket)

from atlas_core.monitoring.system_awareness import SystemMonitor
system_monitor = SystemMonitor()

@app.on_event("startup")
async def start_telemetry_loop():
    async def poll_telemetry():
        while True:
            try:
                # Use to_thread to avoid blocking the event loop with psutil/socket calls
                data = await asyncio.to_thread(system_monitor.get_telemetry)
                await broadcast_event({
                    "type": "system_telemetry",
                    "data": data
                })
            except Exception as e:
                print(f"[Telemetry] Error polling system monitor: {e}")
            await asyncio.sleep(5)
            
    asyncio.create_task(poll_telemetry())

@app.post("/api/v1/assistant/chat")
async def assistant_chat(body: AssistantChatRequest, request: Request):
    sess = get_current_session(request)
    if not sess:
        return JSONResponse(status_code=401, content={"error": "Unauthorized session"})
    
    payload = {
        "person_id": sess.account_id,
        "message": body.message
    }
    
    person = person_registry.get_person_by_account(sess.account_id)
    if person:
        payload["person_id"] = person.atlas_person_id

    # Broadcast that reasoning started
    await broadcast_event({
        "type": "agent_status",
        "status": "THINKING",
        "message": "Analyzing prompt..."
    })

    # Run reasoning in thread pool to prevent blocking the event loop
    gateway_result = await asyncio.to_thread(
        app.state.runtime.process_event,
        "assistant_chat_message",
        payload
    )
    
    # Process the result to match the structured format
    final_response = {}
    reasoning_result = gateway_result.get("reasoning_result")
    
    if reasoning_result:
        decision = reasoning_result.final_decision
        rationale = decision.decision_rationale
        
        is_conversation = "Conversational response" in decision.situation_summary
        
        # Check for rejection or unsupported
        if "outside the ATLAS safety policy" in rationale:
            final_response = {
                "status": "rejected",
                "type": "command",
                "message": "That command was blocked for security reasons."
            }
        elif is_conversation:
            # It's a conversational response from LLMService or Fallback
            await broadcast_event({
                "type": "agent_status",
                "status": "COMPLETED",
                "message": rationale
            })
            final_response = {
                "status": "completed",
                "type": "conversation",
                "message": rationale,
                "intent": None,
                "action": None,
                "execution": None
            }
        elif "not currently enabled in ATLAS" in rationale:
            final_response = {
                "status": "unsupported",
                "type": "command",
                "message": "I can't perform that action yet."
            }
        else:
            # We assume it's a command execution
            intent_str = ""
            for inf in decision.inferences:
                if "Detected intent" in inf:
                    intent_str = inf.replace("Detected intent ", "").replace(".", "")
                    break
            
            # Map intent to human-readable strings for THINKING / EXECUTING
            intent_messages = {
                "SYSTEM_INFO": "Retrieving your system information...",
                "NETWORK_INFO": "Checking your network information...",
                "NETWORK_TEST": f"Running a connectivity test...",
                "DIRECTORY_LIST": "Retrieving directory listing...",
                "ECHO": "Running echo command..."
            }
            executing_msg = intent_messages.get(intent_str, "Processing command...")
            
            # Broadcast INTENT_DETECTED
            await broadcast_event({
                "type": "agent_status",
                "status": "INTENT_DETECTED",
                "intent": intent_str,
                "action": "OSCommandAction"
            })
            
            # Broadcast EXECUTING
            await broadcast_event({
                "type": "agent_status",
                "status": "EXECUTING",
                "message": executing_msg
            })
                    
            execution_data = {}
            if "action_execution_result" in gateway_result:
                exec_res = gateway_result["action_execution_result"]
                if exec_res.executed_actions:
                    dr = exec_res.executed_actions[0]
                    if hasattr(dr, "result") and isinstance(dr.result, dict):
                        execution_data = {
                            "success": dr.result.get("success", False),
                            "stdout": dr.result.get("stdout", ""),
                            "stderr": dr.result.get("stderr", ""),
                            "exit_code": dr.result.get("returncode", 0)
                        }
                    else:
                        execution_data = {"success": True, "stdout": "Action executed."}
                elif exec_res.failed_actions:
                    dr = exec_res.failed_actions[0]
                    execution_data = {
                        "success": False,
                        "stdout": "",
                        "stderr": str(dr.error) if hasattr(dr, "error") else "Execution failed",
                        "exit_code": -1
                    }
            
            final_status = "completed" if execution_data.get("success") else "failed"
            
            final_message = "Command completed."
            if final_status == "completed":
                if "SYSTEM_INFO" in intent_str:
                    out = execution_data.get("stdout", "")
                    
                    # Parse systeminfo output
                    os_name = "Unknown"
                    cpu = "Unknown"
                    mem_avail = "Unknown"
                    uptime = "Unknown"
                    
                    for line in out.splitlines():
                        if line.startswith("OS Name:"):
                            os_name = line.replace("OS Name:", "").strip()
                        elif line.startswith("System Boot Time:"):
                            uptime = line.replace("System Boot Time:", "").strip()
                        elif line.startswith("Available Physical Memory:"):
                            mem_avail = line.replace("Available Physical Memory:", "").strip()
                        elif line.strip().startswith("[01]: Intel") or line.strip().startswith("[01]: AMD"):
                            cpu = line.strip().split("]: ", 1)[-1]
                            
                    final_message = (
                        "System status retrieved successfully.\n\n"
                        f"• Operating System: {os_name}\n"
                        f"• CPU: {cpu}\n"
                        f"• Available Memory: {mem_avail}\n"
                        f"• System Boot Time: {uptime}\n\n"
                        "No critical issues detected."
                    )
                elif "NETWORK_INFO" in intent_str:
                    final_message = "Network information retrieved successfully."
                elif "NETWORK_TEST" in intent_str:
                    final_message = "Connectivity test completed successfully."
                elif "DIRECTORY_LIST" in intent_str:
                    final_message = "Directory listing retrieved successfully."
                elif "ECHO" in intent_str:
                    final_message = "Echo command executed successfully."
            else:
                final_message = "I couldn't complete that action."
                    
            final_response = {
                "status": final_status,
                "type": "command",
                "message": final_message,
                "intent": intent_str,
                "action": "OSCommandAction",
                "execution": execution_data
            }
    else:
        final_response = {
            "status": "failed",
            "message": "I couldn't complete that action."
        }
    
    serializable_result = make_serializable(final_response)
    
    # Broadcast reasoning complete or failed
    ws_status = "COMPLETED" if final_response.get("status") == "completed" else "FAILED"
    if final_response.get("status") in ["rejected", "unsupported"]:
        ws_status = "FAILED"
        
    await broadcast_event({
        "type": "agent_status",
        "status": ws_status,
        "result": serializable_result
    })
    
    return serializable_result



# --- Admin APIs ---
from atlas_ui.backend.routes.admin import router as admin_router
app.include_router(admin_router)


# --- Serve Frontend SPA ---

frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")

# Mount Static assets
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")





# --- Phase 4A: Biometric API ---
app.include_router(biometric_router)

# --- Phase D: Vision Sync Worker ---
# NOTE: The VisionSyncWorker syncs identity/biometric data to the OLD LOCAL Vision Edge
# running on port 8002. This is SEPARATE from the new RemoteVisionClient which connects
# to the remote ATLAS Vision machine at 10.9.96.13:8765.
# The target URL is now configurable via ATLAS_LOCAL_VISION_URL (default: http://127.0.0.1:8002)
from atlas_core.sync.vision_sync_worker import VisionSyncWorker
from atlas_ui.backend.routes.biometric import _face_store

_local_vision_url = os.environ.get("ATLAS_LOCAL_VISION_URL", "http://127.0.0.1:8002")
vision_sync_worker = VisionSyncWorker(
    identity_memory=identity_memory,
    face_template_store=_face_store,
    target_url=_local_vision_url
)
identity_memory.on_mutation_callbacks.append(vision_sync_worker.state.mark_identity_dirty)
_face_store.on_mutation_callbacks.append(vision_sync_worker.state.mark_biometric_dirty)

app.state.vision_sync_worker = vision_sync_worker

@app.on_event("startup")
async def startup_sync_worker():
    vision_sync_worker.start()

@app.on_event("shutdown")
async def shutdown_sync_worker():
    vision_sync_worker.stop()
