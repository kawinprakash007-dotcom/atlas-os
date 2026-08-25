import dataclasses
from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from atlas_core.events.event import Event
from atlas_core.network.schemas import validate_event, ContractValidationError
from atlas_core.network.vision_adapter import VisionEventAdapter

app = FastAPI(title="ATLAS OS Network API", version="1.5.0")

# Placeholder for runtime injection
app.state.runtime = None

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

    # 2. Contract Validation (replaces raw input check)
    try:
        validated_event = validate_event(body)
    except ContractValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Contract validation failed.", "detail": str(e)}
        )

    # 3. Vision Event Adapter Normalization
    try:
        event_type, payload = VisionEventAdapter.normalize(validated_event)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Normalization failed.", "detail": str(e)}
        )

    # 4. Process event in ATLASRuntime
    runtime = request.app.state.runtime
    if runtime is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "ATLAS OS runtime is not initialized."}
        )

    try:
        result = runtime.process_event(event_type, payload)
        safe_result = make_serializable(result)
        return {"status": "success", "result": safe_result}
    except Exception as e:
        # Safely handle unexpected runtime errors and do not expose stack trace
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "Internal runtime error.", "detail": str(e)}
        )
