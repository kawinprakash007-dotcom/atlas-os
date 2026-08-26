import time
from fastapi.testclient import TestClient

from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.monitoring.metrics import SystemMetrics
from atlas_core.monitoring.event_stream import EventStream
from atlas_core.commands.registry import CommandRegistry
from atlas_core.commands.dispatcher import DeviceCommandDispatcher
from atlas_core.commands.manager import DeviceCommandManager
from atlas_core.network.server import app

def print_separator(title: str):
    print("\n" + "="*70)
    print(f" {title} ")
    print("="*70)

def print_command_trace(client: TestClient, command_id: str):
    response = client.get(f"/api/v1/commands/{command_id}")
    if response.status_code == 200:
        c = response.json()
        print(f"Command ID:      {c['command_id']}")
        print(f"Target Device:   {c['target_device']}")
        print(f"Command Type:    {c['command_type']}")
        print(f"Status:          {c['status']}")
        print(f"Created At:      {c['created_at']}")
        print(f"Dispatched At:   {c['dispatched_at']}")
        print(f"Acknowledged At: {c['acknowledged_at']}")
        print(f"Completed At:    {c['completed_at']}")
        print(f"Result:          {c['result']}")
        print(f"Error captured:  {c['error']}")
    else:
        print(f"Error retrieving command: {response.text}")

def main():
    print("==================================================")
    print("ATLAS OS v1.8 Unified Command & Control Demo")
    print("==================================================")

    # 1. Setup Shared Composition Root
    device_registry = DeviceRegistry()
    device_health_manager = DeviceHealthManager(device_registry)
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

    # Wire to FastAPI State
    app.state.device_registry = device_registry
    app.state.device_health_manager = device_health_manager
    app.state.system_metrics = system_metrics
    app.state.event_stream = event_stream
    app.state.command_registry = command_registry
    app.state.command_dispatcher = command_dispatcher
    app.state.command_manager = command_manager

    client = TestClient(app)

    # Register transports
    # Success mock transport
    def led_success_transport(command, device):
        return {
            "acknowledged": True,
            "success": True,
            "result": {"status": "led_set_success", "color": command.payload.get("color")}
        }

    # Reject mock transport
    def reject_transport(command, device):
        return {
            "acknowledged": True,
            "success": False,
            "error": "Hardware busy, command execution rejected by device pin."
        }

    # Exception mock transport
    def crashing_transport(command, device):
        raise ConnectionError("ESP32 transport lost socket connection during write.")

    command_dispatcher.register_transport("esp32", led_success_transport)
    command_dispatcher.register_transport("raspberrypi", reject_transport)
    command_dispatcher.register_transport("drone", crashing_transport)

    # --------------------------------------------------
    # SCENARIO 1 — Registered ONLINE Device
    # --------------------------------------------------
    print_separator("SCENARIO 1 — Registered ONLINE Device -> Success")
    device_registry.register_device("esp32_01", "esp32")
    device_registry.record_heartbeat("esp32_01")
    # Evaluate so it is ONLINE
    device_health_manager.evaluate_device("esp32_01")

    response = client.post("/api/v1/commands", json={
        "target_device": "esp32_01",
        "command_type": "SET_LED",
        "payload": {"color": "green"}
    })
    print(f"HTTP Status: {response.status_code}")
    cmd_id_1 = response.json().get("command_id")

    print("\n--- Command Lifecycle State ---")
    print_command_trace(client, cmd_id_1)

    # --------------------------------------------------
    # SCENARIO 2 — Unknown Device
    # --------------------------------------------------
    print_separator("SCENARIO 2 — Unknown Device -> REJECTED")

    response = client.post("/api/v1/commands", json={
        "target_device": "unknown_device_99",
        "command_type": "SET_LED",
        "payload": {}
    })
    print(f"HTTP Status: {response.status_code}")
    cmd_id_2 = response.json().get("command_id")

    print("\n--- Command Lifecycle State ---")
    print_command_trace(client, cmd_id_2)

    # --------------------------------------------------
    # SCENARIO 3 — OFFLINE Device
    # --------------------------------------------------
    print_separator("SCENARIO 3 — OFFLINE Device -> REJECTED")
    device_registry.register_device("esp32_offline", "esp32")
    # Manually shift last_seen backward in the registry to simulate elapsed offline time
    device_registry.update_device("esp32_offline", last_seen=time.time() - 200.0)

    response = client.post("/api/v1/commands", json={
        "target_device": "esp32_offline",
        "command_type": "SET_LED",
        "payload": {}
    })
    print(f"HTTP Status: {response.status_code}")
    cmd_id_3 = response.json().get("command_id")

    print("\n--- Command Lifecycle State ---")
    print_command_trace(client, cmd_id_3)

    # --------------------------------------------------
    # SCENARIO 4 — Device Rejects Command (success = False)
    # --------------------------------------------------
    print_separator("SCENARIO 4 — Device Rejects Command -> FAILED")
    device_registry.register_device("rpi_01", "raspberrypi")
    device_registry.record_heartbeat("rpi_01")
    device_health_manager.evaluate_device("rpi_01")

    response = client.post("/api/v1/commands", json={
        "target_device": "rpi_01",
        "command_type": "TRIGGER_RELAY",
        "payload": {"relay_index": 2}
    })
    print(f"HTTP Status: {response.status_code}")
    cmd_id_4 = response.json().get("command_id")

    print("\n--- Command Lifecycle State ---")
    print_command_trace(client, cmd_id_4)

    # --------------------------------------------------
    # SCENARIO 5 — Transport Exception
    # --------------------------------------------------
    print_separator("SCENARIO 5 — Transport Exception -> FAILED Safely")
    device_registry.register_device("drone_01", "drone")
    device_registry.record_heartbeat("drone_01")
    device_health_manager.evaluate_device("drone_01")

    response = client.post("/api/v1/commands", json={
        "target_device": "drone_01",
        "command_type": "TAKEOFF",
        "payload": {}
    })
    print(f"HTTP Status: {response.status_code}")
    cmd_id_5 = response.json().get("command_id")

    print("\n--- Command Lifecycle State ---")
    print_command_trace(client, cmd_id_5)

    # --------------------------------------------------
    # RECENT COMMANDS & METRICS
    # --------------------------------------------------
    print_separator("RECENT COMMANDS LIST")
    resp_recent = client.get("/api/v1/commands/recent?limit=5")
    for item in resp_recent.json():
        print(f"Cmd: {item['command_type']} to {item['target_device']} status is {item['status']}")

    print_separator("SYSTEM METRICS WITH COMMANDS")
    resp_metrics = client.get("/api/v1/system/metrics")
    print(resp_metrics.text)

    print("\nDemonstration completed successfully.")

if __name__ == "__main__":
    main()
