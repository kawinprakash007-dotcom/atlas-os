import dataclasses
from typing import Any, Optional, Dict, List
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from atlas_core.events.event import Event
from atlas_core.network.schemas import validate_event, ContractValidationError, VisionEvent
from atlas_core.network.vision_adapter import VisionEventAdapter

app = FastAPI(title="ATLAS OS Network API", version="1.6.0")

# Placeholders for runtime injection (composition root will inject these)
app.state.runtime = None
app.state.device_registry = None
app.state.device_health_manager = None
app.state.event_stream = None
app.state.system_metrics = None
app.state.command_registry = None
app.state.command_dispatcher = None
app.state.command_manager = None

class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    device_type: str = Field(..., min_length=1)
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DeviceCommandRequest(BaseModel):
    target_device: str = Field(..., min_length=1)
    command_type: str = Field(..., min_length=1)
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

def make_serializable(obj: Any) -> Any:
    """
    Recursively converts custom dataclasses, sets, custom models,
    and Event instances into JSON-serializable python types.
    """
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
    elif isinstance(obj, Event):
        return {
            "event_id": obj.event_id,
            "source": obj.source,
            "event_type": obj.event_type,
            "priority": obj.priority,
            "payload": make_serializable(obj.payload),
            "timestamp": obj.timestamp,
            "metadata": make_serializable(obj.metadata)
        }
    elif hasattr(obj, "model_dump") and callable(obj.model_dump):
        return make_serializable(obj.model_dump())
    else:
        if hasattr(obj, "to_dict") and callable(obj.to_dict):
            try:
                return make_serializable(obj.to_dict())
            except Exception:
                pass
        return obj

@app.get("/")
def read_root():
    return {
        "service": "ATLAS OS",
        "status": "running"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }

@app.post("/api/v1/events")
async def process_network_event(request: Request):
    # 1. Parse JSON body
    try:
        body = await request.json()
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON payload.", "detail": str(e)}
        )

    # 1.5 Extract fields with placeholder fallback if missing or empty
    if isinstance(body, dict):
        raw_event_type = body.get("event_type", "UNKNOWN")
        raw_source = body.get("source", "UNKNOWN")
    else:
        raw_event_type = "UNKNOWN"
        raw_source = "UNKNOWN"

    event_type = raw_event_type if isinstance(raw_event_type, str) and raw_event_type.strip() else "UNKNOWN"
    source = raw_source if isinstance(raw_source, str) and raw_source.strip() else "UNKNOWN"

    # Create EventTrace immediately after receiving valid JSON request
    event_stream = request.app.state.event_stream
    trace_id = None
    if event_stream is not None:
        try:
            trace = event_stream.create_event(event_type=event_type, source=source)
            trace_id = trace.trace_id
        except Exception:
            pass

    # 2. Contract Validation (replaces raw input check)
    try:
        validated_event = validate_event(body)
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_validated(trace_id)
            except Exception:
                pass
    except ContractValidationError as e:
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_rejected(trace_id, error=str(e))
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Contract validation failed.", 
                "detail": str(e),
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    # 2.5 Event Source Validation (Event Source Identity Rule)
    source = validated_event.source

    registry = request.app.state.device_registry
    if registry is None:
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_failed(trace_id, error="Device registry is not initialized.")
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "Device registry is not initialized.",
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    if not registry.device_exists(source):
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_rejected(trace_id, error=f"Unknown event source: '{source}'.")
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": f"Unknown event source: '{source}'.",
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    # Device verified!
    if event_stream is not None and trace_id:
        try:
            event_stream.mark_device_verified(trace_id)
        except Exception:
            pass

    # Update heartbeat for registered source
    try:
        registry.record_heartbeat(source)
    except Exception as e:
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_failed(trace_id, error=f"Failed to update device heartbeat: {str(e)}")
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Failed to update device heartbeat.", 
                "detail": str(e),
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    # 3. Vision Event Adapter Normalization
    try:
        event_type, payload = VisionEventAdapter.normalize(validated_event)
    except Exception as e:
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_failed(trace_id, error=f"Normalization failed: {str(e)}")
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": "Normalization failed.", 
                "detail": str(e),
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    # 4. Process event in ATLASRuntime
    runtime = request.app.state.runtime
    if runtime is None:
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_failed(trace_id, error="ATLAS OS runtime is not initialized.")
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "ATLAS OS runtime is not initialized.",
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

    # Mark PROCESSING
    if event_stream is not None and trace_id:
        try:
            event_stream.mark_processing(trace_id)
        except Exception:
            pass

    try:
        result = runtime.process_event(event_type, payload)
        
        # Success! Mark COMPLETED and extract metrics
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_runtime_result(trace_id, result)
            except Exception:
                pass

        safe_result = make_serializable(result)
        return {
            "status": "success", 
            "result": safe_result,
            **({"trace_id": trace_id} if trace_id else {})
        }
    except Exception as e:
        # Runtime failed!
        if event_stream is not None and trace_id:
            try:
                event_stream.mark_failed(trace_id, error=str(e))
            except Exception:
                pass
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal runtime error.", 
                "detail": str(e),
                **({"trace_id": trace_id} if trace_id else {})
            }
        )

@app.post("/api/v1/devices/register")
async def register_device(request: Request, body: DeviceRegisterRequest):
    registry = request.app.state.device_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Device registry is not initialized."}
        )
    try:
        device = registry.register_device(
            device_id=body.device_id,
            device_type=body.device_type,
            capabilities=body.capabilities,
            metadata=body.metadata
        )
        return make_serializable(device)
    except ValueError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Validation failed.", "detail": str(e)}
        )

@app.post("/api/v1/devices/{device_id}/heartbeat")
async def device_heartbeat(request: Request, device_id: str):
    registry = request.app.state.device_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Device registry is not initialized."}
        )
    if not registry.device_exists(device_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": f"Device '{device_id}' is not registered."}
        )
    try:
        device = registry.record_heartbeat(device_id)
        return make_serializable(device)
    except KeyError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Device not found.", "detail": str(e)}
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Heartbeat registration failed.", "detail": str(e)}
        )

@app.get("/api/v1/devices")
async def list_devices(request: Request):
    registry = request.app.state.device_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Device registry is not initialized."}
        )
    devices = registry.list_devices()
    return make_serializable(devices)

@app.get("/api/v1/devices/{device_id}")
async def get_device(request: Request, device_id: str):
    registry = request.app.state.device_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Device registry is not initialized."}
        )
    device = registry.get_device(device_id)
    if device is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Device '{device_id}' does not exist."}
        )
    return make_serializable(device)

@app.get("/api/v1/system/status")
async def get_system_status(request: Request):
    runtime = request.app.state.runtime
    health_manager = request.app.state.device_health_manager
    metrics = request.app.state.system_metrics
    
    atlas_core_status = "ONLINE" if runtime is not None else "OFFLINE"
    
    reasoner_status = "OFFLINE"
    if runtime is not None:
        pipeline = getattr(runtime, "reasoning_pipeline", None)
        if pipeline is not None and getattr(pipeline, "reasoner", None) is not None:
            reasoner_status = "READY"
            
    network_status = "ONLINE"
    
    if health_manager is not None:
        devices_summary = health_manager.get_system_summary()
    else:
        devices_summary = {"total": 0, "online": 0, "stale": 0, "offline": 0}
        
    monitoring_summary = {
        "total_events": metrics.total_events if metrics is not None else 0
    }

    return {
        "atlas_core": atlas_core_status,
        "reasoner": reasoner_status,
        "network": network_status,
        "devices": devices_summary,
        "monitoring": monitoring_summary
    }

@app.get("/api/v1/events/recent")
async def get_recent_events(request: Request, limit: int = 50):
    event_stream = request.app.state.event_stream
    if event_stream is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Event stream is not initialized."}
        )
    safe_limit = max(1, min(limit, 1000))
    traces = event_stream.list_recent(safe_limit)
    return make_serializable(traces)

@app.get("/api/v1/events/{trace_id}")
async def get_event_trace(request: Request, trace_id: str):
    event_stream = request.app.state.event_stream
    if event_stream is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Event stream is not initialized."}
        )
    trace = event_stream.get_event(trace_id)
    if trace is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Event trace '{trace_id}' not found."}
        )
    return make_serializable(trace)

@app.get("/api/v1/system/metrics")
async def get_system_metrics(request: Request):
    metrics = request.app.state.system_metrics
    if metrics is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "System metrics is not initialized."}
        )
    return metrics.get_summary()

@app.post("/api/v1/commands")
async def issue_device_command(request: Request, body: DeviceCommandRequest):
    manager = request.app.state.command_manager
    if manager is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Command manager is not initialized."}
        )
    
    cmd = manager.send_command(
        target_device=body.target_device,
        command_type=body.command_type,
        payload=body.payload,
        metadata=body.metadata
    )
    
    return make_serializable(cmd)

@app.get("/api/v1/commands/recent")
async def get_recent_commands(request: Request, limit: int = 50):
    registry = request.app.state.command_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Command registry is not initialized."}
        )
    safe_limit = max(1, min(limit, 1000))
    commands = registry.list_recent(safe_limit)
    return make_serializable(commands)

@app.get("/api/v1/commands/{command_id}")
async def get_device_command(request: Request, command_id: str):
    registry = request.app.state.command_registry
    if registry is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "Command registry is not initialized."}
        )
    cmd = registry.get_command(command_id)
    if cmd is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": f"Device command '{command_id}' not found."}
        )
    return make_serializable(cmd)
