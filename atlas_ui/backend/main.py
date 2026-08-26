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




app = FastAPI(title="ATLAS OS User Interface API", version="1.9.0")

# Setup Shared Composition Root Instances
config = UIConfiguration()
# Phase IM4: Initialize SQLite Persistence
from atlas_ui.backend.database.sqlite_store import SQLiteStore
sqlite_store = SQLiteStore()

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
                "required_schema": e.expected_schema,
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
    # Only seed if the database is completely empty
    if len(account_registry.list_accounts()) > 0:
        return
        
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
                if intent_str == "SYSTEM_INFO":
                    final_message = "System information retrieved successfully."
                elif intent_str == "NETWORK_INFO":
                    final_message = "Network information retrieved successfully."
                elif intent_str == "NETWORK_TEST":
                    final_message = "Connectivity test completed successfully."
                elif intent_str == "DIRECTORY_LIST":
                    final_message = "Directory listing retrieved successfully."
                elif intent_str == "ECHO":
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

@app.get("/")
async def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>ATLAS OS Frontend Files Missing</h1>")


# --- Phase 4A: Biometric API ---
app.include_router(biometric_router)

