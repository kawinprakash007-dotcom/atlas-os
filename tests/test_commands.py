import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_core.monitoring.metrics import SystemMetrics
from atlas_core.devices.models import Device
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.commands.models import DeviceCommand
from atlas_core.commands.registry import CommandRegistry
from atlas_core.commands.dispatcher import DeviceCommandDispatcher
from atlas_core.commands.manager import DeviceCommandManager
from atlas_core.network.server import app

@pytest.fixture
def clean_metrics():
    return SystemMetrics()

@pytest.fixture
def clean_device_registry():
    return DeviceRegistry()

@pytest.fixture
def clean_health_manager(clean_device_registry):
    return DeviceHealthManager(clean_device_registry)

@pytest.fixture
def clean_command_registry(clean_metrics):
    return CommandRegistry(max_history=10, metrics=clean_metrics)

@pytest.fixture
def clean_dispatcher():
    return DeviceCommandDispatcher()

@pytest.fixture
def clean_manager(clean_device_registry, clean_command_registry, clean_dispatcher, clean_health_manager):
    return DeviceCommandManager(
        device_registry=clean_device_registry,
        command_registry=clean_command_registry,
        command_dispatcher=clean_dispatcher,
        health_manager=clean_health_manager
    )

@pytest.fixture
def client(clean_device_registry, clean_health_manager, clean_metrics, clean_command_registry, clean_manager):
    app.state.device_registry = clean_device_registry
    app.state.device_health_manager = clean_health_manager
    app.state.system_metrics = clean_metrics
    app.state.command_registry = clean_command_registry
    app.state.command_manager = clean_manager
    yield TestClient(app)
    app.state.device_registry = None
    app.state.device_health_manager = None
    app.state.system_metrics = None
    app.state.command_registry = None
    app.state.command_manager = None


# 1. Command creation
def test_command_creation(clean_command_registry):
    cmd = clean_command_registry.create_command("device_1", "SET_SPEED", {"val": 10})
    assert cmd.command_id is not None
    assert cmd.target_device == "device_1"
    assert cmd.command_type == "SET_SPEED"
    assert cmd.payload == {"val": 10}
    assert cmd.status == "PENDING"
    assert cmd.created_at > 0


# 2. UUID uniqueness
def test_command_uuid_uniqueness(clean_command_registry):
    c1 = clean_command_registry.create_command("dev", "T1")
    c2 = clean_command_registry.create_command("dev", "T2")
    assert c1.command_id != c2.command_id


# 3. Command lookup
def test_command_lookup(clean_command_registry):
    c1 = clean_command_registry.create_command("dev", "T1")
    retrieved = clean_command_registry.get_command(c1.command_id)
    assert retrieved is not None
    assert retrieved.command_id == c1.command_id

    assert clean_command_registry.get_command("non_existent_id") is None


# 4. Recent command listing
def test_recent_command_listing(clean_command_registry):
    clean_command_registry.create_command("dev", "T1")
    clean_command_registry.create_command("dev", "T2")
    clean_command_registry.create_command("dev", "T3")

    recent = clean_command_registry.list_recent(limit=2)
    assert len(recent) == 2
    assert recent[0].command_type == "T2"
    assert recent[1].command_type == "T3"


# 5. Bounded command history
def test_bounded_command_history():
    tight_registry = CommandRegistry(max_history=3)
    tight_registry.create_command("dev", "T1")
    tight_registry.create_command("dev", "T2")
    tight_registry.create_command("dev", "T3")

    assert len(tight_registry.list_recent(10)) == 3

    tight_registry.create_command("dev", "T4")
    recent = tight_registry.list_recent(10)
    assert len(recent) == 3
    assert recent[0].command_type == "T2"
    assert recent[1].command_type == "T3"
    assert recent[2].command_type == "T4"
    assert tight_registry.get_command("T1") is None


# 6. Deep-copy / immutability
def test_command_immutability(clean_command_registry):
    cmd = clean_command_registry.create_command("dev", "T1", {"x": 1})
    cmd.payload["x"] = 99
    cmd.status = "COMPLETED"

    internal = clean_command_registry.get_command(cmd.command_id)
    assert internal.status == "PENDING"
    assert internal.payload["x"] == 1


# 7. Unknown device rejection
def test_unknown_device_rejection(clean_manager, clean_metrics):
    # Device not registered in registry
    cmd = clean_manager.send_command("unknown_device", "SHUTDOWN")
    assert cmd.status == "REJECTED"
    assert "not registered" in cmd.error
    assert clean_metrics.commands_rejected == 1


# 8. OFFLINE device rejection
def test_offline_device_rejection(clean_manager, clean_device_registry, clean_health_manager):
    # Register device but mark it as OFFLINE
    clean_device_registry.register_device(device_id="esp_01", device_type="esp32")
    # Simulate elapsed offline time by subtracting from last_seen
    clean_device_registry.update_device("esp_01", last_seen=time.time() - 200.0)

    cmd = clean_manager.send_command("esp_01", "SHUTDOWN")
    assert cmd.status == "REJECTED"
    assert "OFFLINE" in cmd.error


# 9. STALE device rejection
def test_stale_device_rejection(clean_manager, clean_device_registry, clean_health_manager):
    clean_device_registry.register_device(device_id="esp_01", device_type="esp32")
    # Simulate elapsed stale time by subtracting from last_seen
    clean_device_registry.update_device("esp_01", last_seen=time.time() - 80.0)

    cmd = clean_manager.send_command("esp_01", "SHUTDOWN")
    assert cmd.status == "REJECTED"
    assert "STALE" in cmd.error


# 10. Empty target device rejection
def test_empty_target_device_rejection(clean_manager):
    cmd = clean_manager.send_command("", "SHUTDOWN")
    assert cmd.status == "REJECTED"
    assert "target_device" in cmd.error


# 11. Empty command type rejection
def test_empty_command_type_rejection(clean_manager):
    cmd = clean_manager.send_command("dev_1", "")
    assert cmd.status == "REJECTED"
    assert "command_type" in cmd.error


# 12. Successful command dispatch
# 13. Handler acknowledgement
# 14. Successful command completion
def test_successful_command_flow(clean_manager, clean_device_registry, clean_dispatcher, clean_metrics):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    # Register transport handler
    handler_mock = MagicMock(return_value={
        "acknowledged": True,
        "success": True,
        "result": {"status": "led_turned_on"}
    })
    clean_dispatcher.register_transport("esp32", handler_mock)

    cmd = clean_manager.send_command("esp_01", "SET_LED", {"state": "on"})
    
    assert cmd.status == "COMPLETED"
    assert cmd.dispatched_at is not None
    assert cmd.acknowledged_at is not None
    assert cmd.completed_at is not None
    assert cmd.result == {"status": "led_turned_on"}
    assert cmd.error is None

    handler_mock.assert_called_once()
    assert clean_metrics.commands_completed == 1


# 15. Device-level command rejection
def test_device_level_command_rejection(clean_manager, clean_device_registry, clean_dispatcher, clean_metrics):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    handler_mock = MagicMock(return_value={
        "acknowledged": True,
        "success": False,
        "error": "Pin already in use"
    })
    clean_dispatcher.register_transport("esp32", handler_mock)

    cmd = clean_manager.send_command("esp_01", "SET_LED")
    assert cmd.status == "FAILED"
    assert cmd.error == "Pin already in use"
    assert clean_metrics.commands_failed == 1


# 16. Handler exception captured safely
def test_handler_exception_captured_safely(clean_manager, clean_device_registry, clean_dispatcher, clean_metrics):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    # Handler crashes
    def faulty_handler(command, device):
        raise ConnectionResetError("Connection lost")
    clean_dispatcher.register_transport("esp32", faulty_handler)

    cmd = clean_manager.send_command("esp_01", "SET_LED")
    assert cmd.status == "FAILED"
    assert "Connection lost" in cmd.error
    assert clean_metrics.commands_failed == 1


# 17. Invalid lifecycle transition rejected
def test_invalid_lifecycle_transition_rejected(clean_command_registry):
    cmd = clean_command_registry.create_command("dev_1", "T1")
    # PENDING -> EXECUTING directly is not allowed (must go through DISPATCHED)
    with pytest.raises(ValueError, match="Invalid transition"):
        clean_command_registry.update_status(cmd.command_id, "EXECUTING")


# 18. Terminal state cannot transition
def test_terminal_state_cannot_transition(clean_command_registry):
    cmd = clean_command_registry.create_command("dev_1", "T1")
    clean_command_registry.update_status(cmd.command_id, "REJECTED", error="some error")
    with pytest.raises(ValueError, match="Cannot transition"):
        clean_command_registry.update_status(cmd.command_id, "COMPLETED")


# 19. Command metrics consistency
def test_command_metrics_consistency(clean_command_registry, clean_metrics):
    c1 = clean_command_registry.create_command("dev", "T1")
    assert clean_metrics.commands_total == 1
    
    clean_command_registry.update_status(c1.command_id, "REJECTED")
    assert clean_metrics.commands_rejected == 1
    assert clean_metrics.commands_completed == 0


# --- HTTP APIs ---

# 20. POST command API
def test_post_command_api(client, clean_device_registry, clean_dispatcher):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    clean_dispatcher.register_transport("esp32", lambda cmd, dev: {"success": True, "result": {"ack": True}})

    response = client.post("/api/v1/commands", json={
        "target_device": "esp_01",
        "command_type": "SET_MOTOR",
        "payload": {"speed": 40}
    })
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert response.json()["result"] == {"ack": True}


# 21. GET recent commands API
def test_get_recent_commands_api(client, clean_device_registry):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    client.post("/api/v1/commands", json={"target_device": "esp_01", "command_type": "SET_MOTOR"})

    response = client.get("/api/v1/commands/recent?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["command_type"] == "SET_MOTOR"


# 22. GET command by ID API
# 23. Unknown command returns 404
def test_get_command_by_id_api(client, clean_device_registry):
    clean_device_registry.register_device("esp_01", "esp32")
    clean_device_registry.record_heartbeat("esp_01")

    resp = client.post("/api/v1/commands", json={"target_device": "esp_01", "command_type": "SET_MOTOR"})
    cmd_id = resp.json()["command_id"]

    response = client.get(f"/api/v1/commands/{cmd_id}")
    assert response.status_code == 200
    assert response.json()["command_id"] == cmd_id

    # 23. Unknown command
    resp404 = client.get("/api/v1/commands/non_existent_id")
    assert resp404.status_code == 404
