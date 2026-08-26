import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_core.devices.models import Device
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.network.server import app
from atlas_core.runtime.atlas_runtime import ATLASRuntime


@pytest.fixture
def clean_registry():
    return DeviceRegistry()


@pytest.fixture
def clean_health_manager(clean_registry):
    return DeviceHealthManager(clean_registry, stale_threshold=5.0, offline_threshold=10.0)


@pytest.fixture
def client(clean_registry, clean_health_manager):
    app.state.device_registry = clean_registry
    app.state.device_health_manager = clean_health_manager
    yield TestClient(app)
    app.state.device_registry = None
    app.state.device_health_manager = None
    app.state.runtime = None


@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=ATLASRuntime)
    runtime.process_event.return_value = {"status": "success", "mocked": True}
    app.state.runtime = runtime
    yield runtime
    app.state.runtime = None


# 1. Device Registration & Validation
def test_device_registration_success(clean_registry):
    device = clean_registry.register_device(
        device_id="dev_01",
        device_type="camera",
        capabilities=["video", "audio"],
        metadata={"location": "lobby"}
    )
    assert device.device_id == "dev_01"
    assert device.device_type == "camera"
    assert "video" in device.capabilities
    assert device.status == "ONLINE"
    assert device.metadata == {"location": "lobby"}
    assert device.registered_at > 0
    assert device.last_seen > 0

    # Validation errors
    with pytest.raises(ValueError, match="device_id must be a non-empty string"):
        clean_registry.register_device("", "camera")
    with pytest.raises(ValueError, match="device_type must be a non-empty string"):
        clean_registry.register_device("dev_01", "")


# 2. Device Lookup & Exists
def test_device_lookup(clean_registry):
    clean_registry.register_device("dev_01", "camera")
    assert clean_registry.device_exists("dev_01") is True
    assert clean_registry.device_exists("dev_unknown") is False

    device = clean_registry.get_device("dev_01")
    assert device is not None
    assert device.device_id == "dev_01"

    assert clean_registry.get_device("dev_unknown") is None


# 3. Duplicate Registration Behavior
def test_duplicate_registration(clean_registry):
    clean_registry.register_device(
        device_id="dev_01",
        device_type="camera",
        capabilities=["video"],
        metadata={"v": 1}
    )

    # Re-registering with the same type updates capabilities, metadata, status, last_seen
    time.sleep(0.01)  # small pause to ensure last_seen update is detectable
    updated = clean_registry.register_device(
        device_id="dev_01",
        device_type="camera",
        capabilities=["video", "infrared"],
        metadata={"v": 2, "updated": True}
    )

    assert updated.device_id == "dev_01"
    assert "infrared" in updated.capabilities
    assert updated.metadata == {"v": 2, "updated": True}
    assert updated.status == "ONLINE"

    # Re-registering with a different type must throw ValueError
    with pytest.raises(ValueError, match="already registered with type"):
        clean_registry.register_device("dev_01", "radar")


# 4. Device Heartbeat updates last_seen
def test_device_heartbeat_updates_last_seen(clean_registry):
    dev = clean_registry.register_device("dev_01", "camera")
    original_last_seen = dev.last_seen

    time.sleep(0.01)
    updated = clean_registry.record_heartbeat("dev_01")
    assert updated.last_seen > original_last_seen
    assert updated.status == "ONLINE"


# 5-8. Health Status & Thresholds (ONLINE, STALE, OFFLINE)
def test_health_state_transitions(clean_registry, clean_health_manager):
    # Register device with custom thresholds (5.0s stale, 10.0s offline)
    clean_registry.register_device("dev_01", "camera")
    device = clean_registry.get_device("dev_01")
    base_time = device.last_seen

    # ONLINE state (elapsed < 5.0)
    assert clean_health_manager.evaluate_device("dev_01", current_time=base_time + 4.9) == "ONLINE"
    assert clean_registry.get_device("dev_01").status == "ONLINE"

    # STALE state (5.0 <= elapsed < 10.0)
    assert clean_health_manager.evaluate_device("dev_01", current_time=base_time + 5.0) == "STALE"
    assert clean_registry.get_device("dev_01").status == "STALE"
    assert clean_health_manager.evaluate_device("dev_01", current_time=base_time + 9.9) == "STALE"

    # OFFLINE state (elapsed >= 10.0)
    assert clean_health_manager.evaluate_device("dev_01", current_time=base_time + 10.0) == "OFFLINE"
    assert clean_registry.get_device("dev_01").status == "OFFLINE"
    assert clean_health_manager.evaluate_device("dev_01", current_time=base_time + 100.0) == "OFFLINE"


# 8. Configurable Thresholds
def test_configurable_thresholds(clean_registry):
    # Instantiate manager with custom tight thresholds
    custom_manager = DeviceHealthManager(clean_registry, stale_threshold=1.0, offline_threshold=2.0)
    clean_registry.register_device("dev_01", "camera")
    device = clean_registry.get_device("dev_01")
    base_time = device.last_seen

    assert custom_manager.evaluate_device("dev_01", current_time=base_time + 0.5) == "ONLINE"
    assert custom_manager.evaluate_device("dev_01", current_time=base_time + 1.5) == "STALE"
    assert custom_manager.evaluate_device("dev_01", current_time=base_time + 2.5) == "OFFLINE"


# 9. Unknown device heartbeat rejection
def test_unknown_device_heartbeat_rejection(clean_registry):
    with pytest.raises(KeyError):
        clean_registry.record_heartbeat("dev_unknown")


# 10. Device Listing
def test_device_listing(clean_registry):
    clean_registry.register_device("dev_01", "camera")
    clean_registry.register_device("dev_02", "lidar")
    devices = clean_registry.list_devices()
    assert len(devices) == 2
    ids = {d.device_id for d in devices}
    assert ids == {"dev_01", "dev_02"}


# 11. System Status Summary
def test_system_status_summary(clean_registry, clean_health_manager):
    clean_registry.register_device("dev_01", "camera")
    clean_registry.register_device("dev_02", "lidar")
    clean_registry.register_device("dev_03", "radar")

    device_1 = clean_registry.get_device("dev_01")
    base_time = device_1.last_seen

    # Artificially set different last_seen values using update_device
    clean_registry.update_device("dev_02", last_seen=base_time - 6.0)  # stale (elapsed = 6.0 >= 5.0)
    clean_registry.update_device("dev_03", last_seen=base_time - 12.0) # offline (elapsed = 12.0 >= 10.0)

    summary = clean_health_manager.get_system_summary(current_time=base_time)
    assert summary == {
        "total": 3,
        "online": 1,
        "stale": 1,
        "offline": 1
    }


# 15. Input/Output Immutability
def test_registry_immutability(clean_registry):
    dev = clean_registry.register_device(
        device_id="dev_01",
        device_type="camera",
        capabilities=["video"],
        metadata={"info": "secret"}
    )
    
    # 1. Returned object should be a copy, modifying it shouldn't modify internal registry state
    dev.capabilities.append("audio")
    dev.metadata["info"] = "hacked"
    dev.status = "OFFLINE"

    internal = clean_registry.get_device("dev_01")
    assert "audio" not in internal.capabilities
    assert internal.metadata["info"] == "secret"
    assert internal.status == "ONLINE"

    # 2. Modifying dictionary list_devices output should not mutate internal state
    all_devs = clean_registry.list_devices()
    all_devs[0].capabilities.append("temp")
    
    internal2 = clean_registry.get_device("dev_01")
    assert "temp" not in internal2.capabilities


# --- Network API Tests ---

def test_api_device_registration(client):
    payload = {
        "device_id": "api_dev_01",
        "device_type": "vision",
        "capabilities": ["object_detection"],
        "metadata": {"room": "lab"}
    }
    response = client.post("/api/v1/devices/register", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "api_dev_01"
    assert data["device_type"] == "vision"
    assert data["capabilities"] == ["object_detection"]
    assert data["metadata"] == {"room": "lab"}
    assert data["status"] == "ONLINE"


def test_api_device_heartbeat(client):
    # Register first
    client.post("/api/v1/devices/register", json={"device_id": "api_dev_01", "device_type": "vision"})

    # Heartbeat
    response = client.post("/api/v1/devices/api_dev_01/heartbeat")
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "api_dev_01"
    assert data["status"] == "ONLINE"

    # Unknown device heartbeat rejection
    response2 = client.post("/api/v1/devices/api_dev_unknown/heartbeat")
    assert response2.status_code == 400
    assert "not registered" in response2.json()["error"]


def test_api_device_lookup_endpoints(client):
    client.post("/api/v1/devices/register", json={"device_id": "d1", "device_type": "typeA"})
    client.post("/api/v1/devices/register", json={"device_id": "d2", "device_type": "typeB"})

    # List all
    response = client.get("/api/v1/devices")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Get one
    response = client.get("/api/v1/devices/d1")
    assert response.status_code == 200
    assert response.json()["device_id"] == "d1"

    # Get unknown
    response = client.get("/api/v1/devices/d_unknown")
    assert response.status_code == 404
    assert "does not exist" in response.json()["error"]


def test_api_system_status_endpoint(client, mock_runtime):
    client.post("/api/v1/devices/register", json={"device_id": "d1", "device_type": "typeA"})
    
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert data["atlas_core"] == "ONLINE"
    assert data["network"] == "ONLINE"
    # reasoner mock: spec has reasoning_pipeline? Spec on ATLASRuntime Mock has it if defined.
    # Let's verify we set it properly in mock_runtime or handle it gracefully
    mock_runtime.reasoning_pipeline = MagicMock()
    mock_runtime.reasoning_pipeline.reasoner = MagicMock()
    
    response2 = client.get("/api/v1/system/status")
    data2 = response2.json()
    assert data2["reasoner"] == "READY"
    assert data2["devices"]["total"] == 1


# 12-14. Event Validation and Runtime Integration
def test_network_event_source_validation(client, mock_runtime):
    # Register device
    client.post("/api/v1/devices/register", json={"device_id": "atlas_vision_01", "device_type": "vision"})

    # 12. Registered device event successfully reaches runtime
    payload_registered = {
        "event_type": "person_entered",
        "source": "atlas_vision_01",
        "payload": {
            "confidence": 0.99
        }
    }
    response1 = client.post("/api/v1/events", json=payload_registered)
    assert response1.status_code == 200
    assert response1.json()["status"] == "success"
    mock_runtime.process_event.assert_called_once()
    mock_runtime.process_event.reset_mock()

    # 14. Event processing updates device last_seen
    device_before = app.state.device_registry.get_device("atlas_vision_01")
    last_seen_before = device_before.last_seen
    time.sleep(0.01)
    
    response_hb = client.post("/api/v1/events", json=payload_registered)
    assert response_hb.status_code == 200
    mock_runtime.process_event.assert_called_once()
    mock_runtime.process_event.reset_mock()
    
    device_after = app.state.device_registry.get_device("atlas_vision_01")
    assert device_after.last_seen > last_seen_before

    # 13. Unknown device event is blocked before runtime
    payload_unknown = {
        "event_type": "person_entered",
        "source": "unknown_device_01",
        "payload": {}
    }
    response2 = client.post("/api/v1/events", json=payload_unknown)
    assert response2.status_code == 400
    assert "Unknown event source" in response2.json()["error"]
    mock_runtime.process_event.assert_not_called()

    # Missing source parameter is blocked
    payload_no_source = {
        "event_type": "person_entered",
        "payload": {}
    }
    response3 = client.post("/api/v1/events", json=payload_no_source)
    assert response3.status_code == 400
    assert "Missing top-level event source" in response3.json()["detail"]
    mock_runtime.process_event.assert_not_called()
