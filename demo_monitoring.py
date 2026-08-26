from dataclasses import dataclass
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.monitoring.metrics import SystemMetrics
from atlas_core.monitoring.event_stream import EventStream
from atlas_core.network.server import app

@dataclass
class MockArbitrationResult:
    verdict: str

@dataclass
class MockReasoningResult:
    arbitration_result: MockArbitrationResult

@dataclass
class MockAction:
    action_type: str
    status: str
    error: str = None

@dataclass
class MockActionExecutionResult:
    executed_actions: list
    failed_actions: list

def print_separator(title: str):
    print("\n" + "="*70)
    print(f" {title} ")
    print("="*70)

def print_trace_lifecycle(client: TestClient, trace_id: str):
    response = client.get(f"/api/v1/events/{trace_id}")
    if response.status_code == 200:
        t = response.json()
        print(f"Trace ID:        {t['trace_id']}")
        print(f"Event Type:      {t['event_type']}")
        print(f"Source:          {t['source']}")
        print(f"Status:          {t['status']}")
        print(f"Validated:       {t['validated']}")
        print(f"Device Verified: {t['device_verified']}")
        print(f"Verdict:         {t['verdict']}")
        print(f"Action Status:   {t['action_status']}")
        if t['error']:
            print(f"Error captured:  {t['error']}")
    else:
        print(f"Could not retrieve trace: {response.text}")

def main():
    print("==================================================")
    print("ATLAS OS v1.7 Live Event Stream & Monitoring Demo")
    print("==================================================")

    # 1. Setup Composition
    device_registry = DeviceRegistry()
    device_health_manager = DeviceHealthManager(device_registry)
    system_metrics = SystemMetrics()
    event_stream = EventStream(metrics=system_metrics)

    # Inject mock runtime to return controlled results for the scenarios
    mock_runtime = MagicMock(spec=ATLASRuntime)
    
    app.state.runtime = mock_runtime
    app.state.device_registry = device_registry
    app.state.device_health_manager = device_health_manager
    app.state.event_stream = event_stream
    app.state.system_metrics = system_metrics

    client = TestClient(app)

    # Register our standard demonstration device
    client.post("/api/v1/devices/register", json={
        "device_id": "atlas_vision_01",
        "device_type": "vision"
    })

    # --------------------------------------------------
    # SCENARIO 1 — Registered Device -> Valid Event -> APPROVED
    # --------------------------------------------------
    print_separator("SCENARIO 1 — Registered Device -> APPROVED")
    
    # Configure mock runtime to return approved verdict and executed action status
    mock_runtime.process_event.return_value = {
        "reasoning_result": MockReasoningResult(MockArbitrationResult("APPROVED")),
        "action_execution_result": MockActionExecutionResult(
            executed_actions=[MockAction("dispatch_security", "SUCCESS")],
            failed_actions=[]
        )
    }

    event_payload = {
        "event_type": "person_entered",
        "source": "atlas_vision_01",
        "payload": {"anonymous_person_id": "ATLAS-P001"}
    }
    
    response = client.post("/api/v1/events", json=event_payload)
    print(f"HTTP Status: {response.status_code}")
    trace_id_1 = response.json().get("trace_id")
    
    print("\n--- Event Lifecycle State ---")
    print_trace_lifecycle(client, trace_id_1)

    # --------------------------------------------------
    # SCENARIO 2 — Registered Device -> REVIEW
    # --------------------------------------------------
    print_separator("SCENARIO 2 — Registered Device -> REVIEW")

    # Configure mock runtime to return REVIEW verdict (which executes no actions)
    mock_runtime.process_event.return_value = {
        "reasoning_result": MockReasoningResult(MockArbitrationResult("REVIEW")),
        "action_execution_result": MockActionExecutionResult(
            executed_actions=[],
            failed_actions=[]
        )
    }

    event_payload_2 = {
        "event_type": "object_moved",
        "source": "atlas_vision_01",
        "payload": {"object_id": "box_01"}
    }

    response = client.post("/api/v1/events", json=event_payload_2)
    print(f"HTTP Status: {response.status_code}")
    trace_id_2 = response.json().get("trace_id")

    print("\n--- Event Lifecycle State ---")
    print_trace_lifecycle(client, trace_id_2)

    # --------------------------------------------------
    # SCENARIO 3 — Unknown Device
    # --------------------------------------------------
    print_separator("SCENARIO 3 — Unknown Device (Rejected before Runtime)")

    event_payload_3 = {
        "event_type": "person_entered",
        "source": "unregistered_cam",
        "payload": {}
    }

    response = client.post("/api/v1/events", json=event_payload_3)
    print(f"HTTP Status: {response.status_code}")
    trace_id_3 = response.json().get("trace_id")

    print("\n--- Event Lifecycle State ---")
    print_trace_lifecycle(client, trace_id_3)

    # --------------------------------------------------
    # SCENARIO 4 — Runtime/Action Failure
    # --------------------------------------------------
    print_separator("SCENARIO 4 — Action Execution Failure")

    # Configure mock runtime to return approved verdict but a failed action outcome
    mock_runtime.process_event.return_value = {
        "reasoning_result": MockReasoningResult(MockArbitrationResult("APPROVED")),
        "action_execution_result": MockActionExecutionResult(
            executed_actions=[],
            failed_actions=[MockAction("alarm_siren", "FAILED", "Hardware Offline")]
        )
    }

    event_payload_4 = {
        "event_type": "smoke_detected",
        "source": "atlas_vision_01",
        "payload": {}
    }

    response = client.post("/api/v1/events", json=event_payload_4)
    print(f"HTTP Status: {response.status_code}")
    trace_id_4 = response.json().get("trace_id")

    print("\n--- Event Lifecycle State ---")
    print_trace_lifecycle(client, trace_id_4)

    # --------------------------------------------------
    # SYSTEM METRICS SUMMARY
    # --------------------------------------------------
    print_separator("CUMULATIVE SYSTEM METRICS")

    response_metrics = client.get("/api/v1/system/metrics")
    print(response_metrics.text)

    print("\nDemonstration completed successfully.")

if __name__ == "__main__":
    main()
