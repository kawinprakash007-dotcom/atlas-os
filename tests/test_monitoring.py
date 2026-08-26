import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_core.monitoring.models import EventTrace
from atlas_core.monitoring.metrics import SystemMetrics
from atlas_core.monitoring.event_stream import EventStream
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.network.server import app
from atlas_core.runtime.atlas_runtime import ATLASRuntime


@pytest.fixture
def clean_metrics():
    return SystemMetrics()


@pytest.fixture
def clean_stream(clean_metrics):
    return EventStream(max_history=10, metrics=clean_metrics)


@pytest.fixture
def clean_registry():
    return DeviceRegistry()


@pytest.fixture
def clean_health_manager(clean_registry):
    return DeviceHealthManager(clean_registry)


@pytest.fixture
def client(clean_registry, clean_health_manager, clean_metrics, clean_stream):
    app.state.device_registry = clean_registry
    app.state.device_health_manager = clean_health_manager
    app.state.event_stream = clean_stream
    app.state.system_metrics = clean_metrics
    yield TestClient(app)
    app.state.device_registry = None
    app.state.device_health_manager = None
    app.state.event_stream = None
    app.state.system_metrics = None
    app.state.runtime = None


@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=ATLASRuntime)
    runtime.process_event.return_value = {"status": "success", "mocked": True}
    app.state.runtime = runtime
    yield runtime
    app.state.runtime = None


# 1. Event trace creation
def test_event_trace_creation(clean_stream):
    trace = clean_stream.create_event(event_type="test_event", source="device_01")
    assert trace.trace_id is not None
    assert trace.event_type == "test_event"
    assert trace.source == "device_01"
    assert trace.status == "RECEIVED"
    assert trace.received_at > 0


# 2. UUID trace IDs are unique
def test_uuid_uniqueness(clean_stream):
    t1 = clean_stream.create_event("e1", "s1")
    t2 = clean_stream.create_event("e2", "s2")
    assert t1.trace_id != t2.trace_id


# 3. Event trace retrieval
def test_event_trace_retrieval(clean_stream):
    t1 = clean_stream.create_event("e1", "s1")
    retrieved = clean_stream.get_event(t1.trace_id)
    assert retrieved is not None
    assert retrieved.trace_id == t1.trace_id

    assert clean_stream.get_event("non_existent_id") is None


# 4. Recent event listing
def test_recent_event_listing(clean_stream):
    clean_stream.create_event("e1", "s1")
    clean_stream.create_event("e2", "s2")
    clean_stream.create_event("e3", "s3")

    recent = clean_stream.list_recent(limit=2)
    assert len(recent) == 2
    # list_recent returns the last limit events
    assert recent[0].event_type == "e2"
    assert recent[1].event_type == "e3"


# 5. Event stream maximum size (bounds behavior at configured max_history)
def test_event_stream_maximum_size():
    tight_stream = EventStream(max_history=3)
    tight_stream.create_event("e1", "s1")
    tight_stream.create_event("e2", "s2")
    tight_stream.create_event("e3", "s3")

    # Limit not exceeded yet
    assert len(tight_stream.list_recent(10)) == 3

    # Add 4th event, oldest (e1) should be discarded
    t4 = tight_stream.create_event("e4", "s4")
    recent = tight_stream.list_recent(10)
    assert len(recent) == 3
    assert recent[0].event_type == "e2"
    assert recent[1].event_type == "e3"
    assert recent[2].event_type == "e4"

    # Querying discarded trace returns None
    assert tight_stream.get_event("e1") is None


# 6. Returned traces are immutable/deep copied
def test_traces_immutability(clean_stream):
    t1 = clean_stream.create_event("e1", "s1")
    t1.metadata["hack"] = True
    t1.status = "COMPLETED"

    # Verify internal trace was not changed
    internal = clean_stream.get_event(t1.trace_id)
    assert internal.status == "RECEIVED"
    assert "hack" not in internal.metadata


# 7. Valid event lifecycle
def test_valid_event_lifecycle(clean_stream):
    trace = clean_stream.create_event("e1", "s1")
    trace_id = trace.trace_id

    # 1. RECEIVED -> VALIDATED
    trace = clean_stream.mark_validated(trace_id)
    assert trace.status == "VALIDATED"
    assert trace.validated is True

    # 2. VALIDATED -> DEVICE_VERIFIED
    trace = clean_stream.mark_device_verified(trace_id)
    assert trace.status == "DEVICE_VERIFIED"
    assert trace.device_verified is True

    # 3. DEVICE_VERIFIED -> PROCESSING
    trace = clean_stream.mark_processing(trace_id)
    assert trace.status == "PROCESSING"

    # 4. PROCESSING -> COMPLETED (success result)
    result = {
        "reasoning_result": MagicMock(
            arbitration_result=MagicMock(verdict="APPROVED")
        ),
        "action_execution_result": MagicMock(
            executed_actions=[MagicMock()],
            failed_actions=[]
        )
    }
    trace = clean_stream.mark_runtime_result(trace_id, result)
    assert trace.status == "COMPLETED"
    assert trace.verdict == "APPROVED"
    assert trace.action_status == "EXECUTED"
    assert trace.completed_at > 0

    # 5. Terminal check: cannot transition out of terminal state
    with pytest.raises(ValueError, match="Cannot transition"):
        clean_stream.mark_validated(trace_id)


# 8. Schema rejected event lifecycle
def test_schema_rejected_lifecycle(clean_stream):
    trace = clean_stream.create_event("e1", "s1")
    trace_id = trace.trace_id

    trace = clean_stream.mark_rejected(trace_id, error="Validation failed")
    assert trace.status == "REJECTED"
    assert trace.error == "Validation failed"
    assert trace.completed_at > 0

    with pytest.raises(ValueError):
        clean_stream.mark_processing(trace_id)


# 9. Unknown device rejected lifecycle
def test_unknown_device_rejected_lifecycle(clean_stream):
    trace = clean_stream.create_event("e1", "s1")
    trace_id = trace.trace_id

    trace = clean_stream.mark_validated(trace_id)
    # Failed device verification -> REJECTED
    trace = clean_stream.mark_rejected(trace_id, error="Unknown device")
    assert trace.status == "REJECTED"
    assert trace.error == "Unknown device"


# 10. Runtime exception creates FAILED trace
def test_runtime_exception_creates_failed_trace(clean_stream):
    trace = clean_stream.create_event("e1", "s1")
    trace_id = trace.trace_id

    trace = clean_stream.mark_validated(trace_id)
    trace = clean_stream.mark_device_verified(trace_id)
    trace = clean_stream.mark_processing(trace_id)

    # Runtime exception -> FAILED
    trace = clean_stream.mark_failed(trace_id, error="Internal DB error")
    assert trace.status == "FAILED"
    assert trace.error == "Internal DB error"


# 11-13. Verdict metrics (APPROVED, REVIEW, BLOCKED)
def test_verdict_metrics(clean_stream, clean_metrics):
    # APPROVED
    t1 = clean_stream.create_event("e1", "s1")
    res_approved = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="APPROVED")),
        "action_execution_result": MagicMock(executed_actions=[MagicMock()], failed_actions=[])
    }
    clean_stream.mark_runtime_result(t1.trace_id, res_approved)
    assert clean_metrics.approved_events == 1

    # REVIEW
    t2 = clean_stream.create_event("e2", "s2")
    res_review = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="REVIEW")),
        "action_execution_result": MagicMock(executed_actions=[], failed_actions=[])
    }
    clean_stream.mark_runtime_result(t2.trace_id, res_review)
    assert clean_metrics.review_events == 1

    # BLOCKED
    t3 = clean_stream.create_event("e3", "s3")
    res_blocked = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="BLOCKED")),
        "action_execution_result": MagicMock(executed_actions=[], failed_actions=[])
    }
    clean_stream.mark_runtime_result(t3.trace_id, res_blocked)
    assert clean_metrics.blocked_events == 1


# 14-16. Action outcome metrics (EXECUTED, FAILED, NO_ACTION)
def test_action_outcome_metrics(clean_stream, clean_metrics):
    # EXECUTED
    t1 = clean_stream.create_event("e1", "s1")
    res_exec = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="APPROVED")),
        "action_execution_result": MagicMock(executed_actions=[MagicMock()], failed_actions=[])
    }
    clean_stream.mark_runtime_result(t1.trace_id, res_exec)
    assert clean_metrics.actions_executed == 1

    # FAILED
    t2 = clean_stream.create_event("e2", "s2")
    res_failed = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="APPROVED")),
        "action_execution_result": MagicMock(executed_actions=[], failed_actions=[MagicMock()])
    }
    clean_stream.mark_runtime_result(t2.trace_id, res_failed)
    assert clean_metrics.actions_failed == 1

    # NO_ACTION
    t3 = clean_stream.create_event("e3", "s3")
    res_noaction = {
        "reasoning_result": MagicMock(arbitration_result=MagicMock(verdict="REVIEW")),
        "action_execution_result": MagicMock(executed_actions=[], failed_actions=[])
    }
    clean_stream.mark_runtime_result(t3.trace_id, res_noaction)
    assert clean_metrics.no_action_events == 1


# --- API Endpoints ---

# 17. GET recent events endpoint
def test_api_recent_events(client):
    # Register and send a valid event to populate stream
    client.post("/api/v1/devices/register", json={"device_id": "lab_cam", "device_type": "vision"})
    client.post("/api/v1/events", json={"event_type": "p_enter", "source": "lab_cam"})

    response = client.get("/api/v1/events/recent?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["source"] == "lab_cam"


# 18. GET event by trace ID endpoint
# 19. Unknown trace returns 404
def test_api_get_event_by_trace_id(client):
    client.post("/api/v1/devices/register", json={"device_id": "lab_cam", "device_type": "vision"})
    resp = client.post("/api/v1/events", json={"event_type": "p_enter", "source": "lab_cam"})
    trace_id = resp.json()["trace_id"]

    response = client.get(f"/api/v1/events/{trace_id}")
    assert response.status_code == 200
    assert response.json()["trace_id"] == trace_id

    # 19. Unknown ID
    response404 = client.get("/api/v1/events/unknown_trace_id")
    assert response404.status_code == 404
    assert "not found" in response404.json()["error"]


# 20. GET system metrics endpoint
def test_api_system_metrics(client):
    response = client.get("/api/v1/system/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "events" in data
    assert "verdicts" in data
    assert "actions" in data


# 21. trace_id exists in normal event responses
def test_trace_id_in_event_responses(client, mock_runtime):
    client.post("/api/v1/devices/register", json={"device_id": "lab_cam", "device_type": "vision"})
    payload = {"event_type": "p_enter", "source": "lab_cam"}
    
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 200
    assert "trace_id" in response.json()
