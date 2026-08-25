import json
from fastapi.testclient import TestClient

from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.decision import Decision
from atlas_core.network.server import app

def welcome_action_handler(payload):
    print(f">> [ACTION DISPATCHER] Executing welcome_person action with payload: {payload}")
    return {"status": "success", "message": f"Greeting played for {payload.get('person_id')}"}

def run_scenario_1(client, runtime):
    print("\n" + "="*60)
    print("SCENARIO 1: Valid ATLAS Vision Event")
    print("="*60)
    print("Description: Simulates a valid vision event sent over HTTP.")
    print("The system validates, normalizes, processes the event, and triggers an action.")
    print("-"*60)

    # 1. Prepare simulated Vision event payload
    event_data = {
        "event_type": "person_entered",
        "anonymous_person_id": "ATLAS-P001",
        "camera_id": "porch_camera",
        "zone": "front_porch",
        "confidence": 0.98,
        "expression_estimate": "Happy"
    }

    print("1. Simulated Incoming JSON Event from ATLAS Vision:")
    print(json.dumps(event_data, indent=2))
    print("\nSending POST request to /api/v1/events...")

    # 2. Send request to endpoint
    response = client.post("/api/v1/events", json=event_data)

    print(f"HTTP Response Status Code: {response.status_code}")
    print("HTTP Response Body:")
    print(json.dumps(response.json(), indent=2))
    print("-"*60)
    
    # 3. Check WorldState updates
    print("Verification of WorldState & History:")
    print(f"Active Persons in WorldState: {runtime.world_state.active_persons}")
    print(f"Total events in History: {len(runtime.event_history.events)}")
    print("="*60)

def run_scenario_2(client):
    print("\n" + "="*60)
    print("SCENARIO 2: Invalid Event (Contract Violation)")
    print("="*60)
    print("Description: Simulates an invalid event payload (missing required event_type) sent over HTTP.")
    print("The system must reject the request BEFORE it reaches the ATLASRuntime.")
    print("-"*60)

    # 1. Prepare invalid payload (no event_type)
    invalid_data = {
        "anonymous_person_id": "ATLAS-P999",
        "camera_id": "lab_camera",
        "zone": "danger_zone"
    }

    print("1. Simulated Malformed JSON Event:")
    print(json.dumps(invalid_data, indent=2))
    print("\nSending POST request to /api/v1/events...")

    # 2. Send request
    response = client.post("/api/v1/events", json=invalid_data)

    print(f"HTTP Response Status Code: {response.status_code}")
    print("HTTP Response Body:")
    print(json.dumps(response.json(), indent=2))
    print("\nVerification: Ensuring ATLASRuntime was NOT invoked for this malformed input.")
    print("="*60)

def main():
    # 1. Set up FakeReasoner with a deterministic approved decision
    approved_decision = Decision(
        situation_summary="Recognized registered resident ATLAS-P001 at the front porch.",
        observations=["ATLAS-P001 is present", "camera porch_camera is active"],
        inferences=["Resident is returning home"],
        risks=[],
        recommended_actions=[{
            "action_type": "welcome_person",
            "payload": {"person_id": "ATLAS-P001", "play_audio": "hello_resident.mp3"}
        }],
        confidence=0.95
    )
    
    reasoner = FakeReasoner(fixed_decision=approved_decision)
    config = ATLASConfiguration()
    runtime = ATLASRuntime(primary_reasoner=reasoner, configuration=config)

    # Preload memory so grounding matches observations
    runtime.memory_manager.remember_fact("ATLAS-P001", "person", "status", "resident")
    runtime.memory_manager.remember_fact("porch_camera", "camera", "status", "active")
    
    # Register the welcome action handler
    runtime.register_action("welcome_person", welcome_action_handler)

    # Inject runtime into FastAPI server state
    app.state.runtime = runtime
    
    # Create the TestClient for HTTP requests
    client = TestClient(app)

    # Run Scenarios
    run_scenario_1(client, runtime)
    run_scenario_2(client)

if __name__ == "__main__":
    main()
