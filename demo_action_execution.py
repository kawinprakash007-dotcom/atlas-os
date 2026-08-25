import json
from atlas_core.actions.registry import ActionRegistry
from atlas_core.actions.safety import ActionSafetyValidator
from atlas_core.actions.dispatcher import ActionDispatcher
from atlas_core.reasoning.arbitration import ArbitrationResult

def print_json(data):
    print(json.dumps(data, indent=2, default=str))

def activate_cooling_handler(payload):
    print(f"  [EXECUTION] Activating cooling for {payload.get('device_id')}...")
    return {"status": "cooling_command_simulated"}

def investigate_handler(payload):
    print(f"  [EXECUTION] Investigating location {payload.get('location')}...")
    return {"status": "investigation_dispatched"}

def main():
    print("==================================================")
    print("ATLAS CORE - ACTION EXECUTION DEMO")
    print("==================================================\n")

    registry = ActionRegistry()
    registry.register("activate_cooling", ["device_id"], activate_cooling_handler)
    registry.register("investigate", ["location"], investigate_handler)

    validator = ActionSafetyValidator(registry)
    dispatcher = ActionDispatcher(registry)

    # --------------------------------------------------
    # SCENARIO 1: APPROVED with valid action
    # --------------------------------------------------
    print("SCENARIO 1: APPROVED verdict, valid registered action")
    print("--------------------------------------------------")
    arb1 = ArbitrationResult(
        verdict="APPROVED",
        approved=True,
        blocked=False,
        requires_human_review=False,
        allowed_actions=[
            {"action_type": "activate_cooling", "payload": {"device_id": "sensor_x"}},
            {"action_type": "investigate", "payload": {"location": "lab_2"}}
        ],
        blocked_actions=[],
        reasons=[],
        confidence=0.9,
        grounding_status="TRUSTED",
        source="primary"
    )
    
    print("Arbitration Output Actions:")
    print_json(arb1.allowed_actions)
    
    safety1 = validator.validate(arb1)
    print(f"\nSafety Validated: {safety1.safe}")
    if safety1.reasons:
        print("Reasons:", safety1.reasons)
        
    print("\nDispatching allowed actions...")
    results1 = dispatcher.dispatch(safety1)
    for res in results1:
        print(f"  Result -> {res.action_type}: {res.status}")
        if res.result:
            print(f"    Payload returned: {res.result}")
            
    print("\n")

    # --------------------------------------------------
    # SCENARIO 2: REVIEW (should block execution)
    # --------------------------------------------------
    print("SCENARIO 2: REVIEW verdict (must not execute)")
    print("--------------------------------------------------")
    arb2 = ArbitrationResult(
        verdict="REVIEW",
        approved=False,
        blocked=False,
        requires_human_review=True,
        allowed_actions=[
            {"action_type": "activate_cooling", "payload": {"device_id": "sensor_x"}}
        ],
        blocked_actions=[],
        reasons=["Confidence is low"],
        confidence=0.6,
        grounding_status="REQUIRES_DEEP_ANALYSIS",
        source="primary"
    )
    
    safety2 = validator.validate(arb2)
    print(f"Safety Validated: {safety2.safe}")
    print("Reasons:", safety2.reasons)
    print(f"Allowed actions passed to dispatcher: {len(safety2.allowed_actions)}")
    print(f"Blocked actions: {len(safety2.blocked_actions)}")
    
    print("\nDispatching allowed actions...")
    results2 = dispatcher.dispatch(safety2)
    print(f"Executed actions: {len(results2)}")
    print("\n")

    # --------------------------------------------------
    # SCENARIO 3: APPROVED but invalid/hallucinated action
    # --------------------------------------------------
    print("SCENARIO 3: APPROVED verdict, but LLM hallucinates action")
    print("--------------------------------------------------")
    arb3 = ArbitrationResult(
        verdict="APPROVED",
        approved=True,
        blocked=False,
        requires_human_review=False,
        allowed_actions=[
            {"action_type": "activate_cooling", "payload": {}}, # Missing device_id
            {"action_type": "call_police", "payload": {"number": "911"}}, # Unknown action
            {"payload": {"some": "data"}}, # Missing action_type
            "not a dictionary" # Invalid structure
        ],
        blocked_actions=[],
        reasons=[],
        confidence=0.9,
        grounding_status="TRUSTED",
        source="primary"
    )
    
    safety3 = validator.validate(arb3)
    print(f"Safety Validated: {safety3.safe}")
    print("Reasons:")
    for r in safety3.reasons:
        print(f"  - {r}")
        
    print(f"\nAllowed actions passed to dispatcher: {len(safety3.allowed_actions)}")
    print(f"Blocked actions intercepted by safety validator: {len(safety3.blocked_actions)}")
    
    print("\nDispatching allowed actions...")
    results3 = dispatcher.dispatch(safety3)
    print(f"Executed actions: {len(results3)}")

if __name__ == "__main__":
    main()
