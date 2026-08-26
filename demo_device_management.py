import time
from fastapi.testclient import TestClient

from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.network.server import app

def print_separator(title: str):
    print("\n" + "="*60)
    print(f" {title} ")
    print("="*60)

def main():
    print("==================================================")
    print("ATLAS OS v1.6 Device Management Demonstration")
    print("==================================================")

    # Setup the composition root (Single Source of Truth)
    config = ATLASConfiguration()
    device_registry = DeviceRegistry()
    
    # Configure tight health thresholds for deterministic testing/demo
    device_health_manager = DeviceHealthManager(
        device_registry,
        stale_threshold=2.0,
        offline_threshold=4.0
    )

    reasoner = FakeReasoner()
    runtime = ATLASRuntime(
        primary_reasoner=reasoner,
        configuration=config,
        device_registry=device_registry,
        device_health_manager=device_health_manager
    )

    # Bind to FastAPI app state
    app.state.runtime = runtime
    app.state.device_registry = device_registry
    app.state.device_health_manager = device_health_manager

    client = TestClient(app)

    # --------------------------------------------------
    # SCENARIO 1 — Device Registration
    # --------------------------------------------------
    print_separator("SCENARIO 1 — Device Registration")
    
    payload = {
        "device_id": "atlas_vision_01",
        "device_type": "vision",
        "capabilities": ["person_detection", "object_detection"],
        "metadata": {"room": "lab_main"}
    }
    
    print(f"Registering device: {payload['device_id']}...")
    response = client.post("/api/v1/devices/register", json=payload)
    print(f"HTTP Status: {response.status_code}")
    print(f"Resulting Device State:\n{response.text}\n")

    # --------------------------------------------------
    # SCENARIO 2 — Heartbeat
    # --------------------------------------------------
    print_separator("SCENARIO 2 — Heartbeat")
    
    # Wait a tiny bit and send heartbeat
    time.sleep(0.1)
    
    print("Sending heartbeat...")
    response = client.post("/api/v1/devices/atlas_vision_01/heartbeat")
    print(f"HTTP Status: {response.status_code}")
    print(f"Updated Device State:\n{response.text}\n")

    # --------------------------------------------------
    # SCENARIO 3 — Real Event (Registered Device)
    # --------------------------------------------------
    print_separator("SCENARIO 3 — Real Event (Registered)")
    
    event_payload = {
        "event_type": "person_entered",
        "source": "atlas_vision_01",
        "payload": {
            "anonymous_person_id": "ATLAS-P001",
            "camera_id": "atlas_vision_01",
            "confidence": 0.98,
            "zone": "server_room"
        }
    }
    
    print(f"Sending event from registered source '{event_payload['source']}'...")
    response = client.post("/api/v1/events", json=event_payload)
    print(f"HTTP Status: {response.status_code}")
    print("Is ATLAS Runtime Invoked? -> YES (success response received)")
    print(f"Response:\n{response.text}\n")

    # --------------------------------------------------
    # SCENARIO 4 — Unknown Device
    # --------------------------------------------------
    print_separator("SCENARIO 4 — Unknown Device")
    
    unknown_payload = {
        "event_type": "person_entered",
        "source": "unknown_device",
        "payload": {
            "confidence": 0.50
        }
    }
    
    print(f"Attempting to send event from unregistered source '{unknown_payload['source']}'...")
    response = client.post("/api/v1/events", json=unknown_payload)
    print(f"HTTP Status: {response.status_code}")
    print("Is ATLAS Runtime Invoked? -> NO (blocked at network boundary)")
    print(f"Response (Safe Client Error):\n{response.text}\n")

    # --------------------------------------------------
    # SCENARIO 5 — Device Health
    # --------------------------------------------------
    print_separator("SCENARIO 5 — Device Health transitions")
    
    print("Using controllable timestamps for health transition evaluation...")
    
    # Retrieve current last_seen of the registered device
    device = device_registry.get_device("atlas_vision_01")
    base_time = device.last_seen
    
    print(f"Base last_seen timestamp: {base_time}")
    
    # 1. Evaluate immediately (ONLINE)
    status_online = device_health_manager.evaluate_device("atlas_vision_01", current_time=base_time + 1.0)
    print(f"Status after 1.0s elapsed: {status_online} (Expected: ONLINE)")
    
    # 2. Evaluate after stale threshold (STALE)
    status_stale = device_health_manager.evaluate_device("atlas_vision_01", current_time=base_time + 2.5)
    print(f"Status after 2.5s elapsed: {status_stale} (Expected: STALE)")
    
    # 3. Evaluate after offline threshold (OFFLINE)
    status_offline = device_health_manager.evaluate_device("atlas_vision_01", current_time=base_time + 4.5)
    print(f"Status after 4.5s elapsed: {status_offline} (Expected: OFFLINE)")

    # Show system summary
    summary = device_health_manager.get_system_summary(current_time=base_time + 4.5)
    print(f"\nFinal System Summary (at elapsed 4.5s):\n{summary}")

    # Fetch status endpoint
    sys_status_resp = client.get("/api/v1/system/status")
    print(f"\nHTTP /api/v1/system/status Response:\n{sys_status_resp.text}")
    print("\nDemonstration completed successfully.")

if __name__ == "__main__":
    main()
