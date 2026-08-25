import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_core.network.schemas import VisionEvent, ContractValidationError, validate_event
from atlas_core.network.vision_adapter import VisionEventAdapter
from atlas_core.network.server import app
from atlas_core.runtime.atlas_runtime import ATLASRuntime

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=ATLASRuntime)
    runtime.process_event.return_value = {"status": "success", "mocked": True}
    app.state.runtime = runtime
    yield runtime
    app.state.runtime = None

# Test 1: GET / and GET /health endpoints work
def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "service": "ATLAS OS",
        "status": "running"
    }

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy"
    }

# Test 2: Valid Vision event is accepted and reaches ATLASRuntime.process_event()
def test_valid_vision_event_accepted(client, mock_runtime):
    payload = {
        "event_type": "person_entered",
        "anonymous_person_id": "ATLAS-P001",
        "camera_id": "lab_cam",
        "confidence": 0.95,
        "zone": "entrance"
    }
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    
    # Check that event reached process_event
    mock_runtime.process_event.assert_called_once()
    called_type, called_payload = mock_runtime.process_event.call_args[0]
    assert called_type == "person_entered"
    
    # Adapter should map anonymous_person_id to person_id
    assert called_payload["person_id"] == "ATLAS-P001"
    assert called_payload["camera_id"] == "lab_cam"

# Test 3: Malformed event (non-JSON body) is rejected
def test_malformed_json_rejected(client, mock_runtime):
    response = client.post("/api/v1/events", content="not json")
    assert response.status_code == 400
    assert "error" in response.json()
    mock_runtime.process_event.assert_not_called()

# Test 4: Reject non-dictionary JSON structures
def test_non_dictionary_rejected(client, mock_runtime):
    response = client.post("/api/v1/events", json=["not a dict"])
    assert response.status_code == 400
    assert "Contract validation failed" in response.json()["error"]
    mock_runtime.process_event.assert_not_called()

# Test 5: Missing required field (event_type) is rejected
def test_missing_required_field_rejected(client, mock_runtime):
    response = client.post("/api/v1/events", json={"person_id": "p1"})
    assert response.status_code == 400
    assert "Contract validation failed" in response.json()["error"]
    mock_runtime.process_event.assert_not_called()

# Test 6: Invalid payload type (payload is not a dict) is rejected
def test_invalid_payload_type_rejected(client, mock_runtime):
    response = client.post("/api/v1/events", json={"event_type": "person_entered", "payload": "not-a-dict"})
    assert response.status_code == 400
    assert "Contract validation failed" in response.json()["error"]
    mock_runtime.process_event.assert_not_called()

# Test 7: Adapter does not mutate input
def test_adapter_does_not_mutate_input():
    event = validate_event({
        "event_type": "person_entered",
        "anonymous_person_id": "ATLAS-P001",
        "camera_id": "lab_cam"
    })
    
    # Call normalization
    event_type, payload = VisionEventAdapter.normalize(event)
    assert event.event_type == "person_entered"
    
    # Mutating payload dictionary returned by adapter should not change event object
    payload["person_id"] = "MUTATED"
    # Re-extract and make sure original is unchanged
    assert event.anonymous_person_id == "ATLAS-P001"

# Test 8: Runtime is not called for invalid input
def test_runtime_not_called_on_invalid_input(client, mock_runtime):
    payload = {"person_id": "p1"}  # Missing event_type
    response = client.post("/api/v1/events", json=payload)
    assert response.status_code == 400
    mock_runtime.process_event.assert_not_called()

# Test 9: Unexpected runtime exception returns a safe server error without trace
def test_unexpected_runtime_exception_returns_safe_error(client, mock_runtime):
    mock_runtime.process_event.side_effect = RuntimeError("Database connection lost!")
    payload = {"event_type": "person_entered", "anonymous_person_id": "p1"}
    response = client.post("/api/v1/events", json=payload)
    
    assert response.status_code == 500
    assert response.json()["error"] == "Internal runtime error."
    # Detail should contain the exception string but not python stack trace
    assert "Database connection lost!" in response.json()["detail"]
