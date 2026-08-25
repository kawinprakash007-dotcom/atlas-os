import json
from typing import Dict, Any

from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.reasoning.decision import Decision

class FakeReasoner:
    def __init__(self, fixed_decision: Decision):
        self.fixed_decision = fixed_decision
    def reason(self, situation: Dict[str, Any], memory: Dict[str, Any]) -> Decision:
        return self.fixed_decision

def print_json(data):
    print(json.dumps(data, indent=2, default=str))

def action_success(payload):
    return {"status": "success", "echo": payload}

def action_fail(payload):
    raise RuntimeError("Intentional handler failure")

def main():
    print("==================================================")
    print("ATLAS CORE v1.5 — UNIFIED RUNTIME DEMO")
    print("==================================================\n")

    scenarios = [
        {
            "name": "SCENARIO 1 — APPROVED",
            "decision": Decision(
                "Sum", "Rat", 
                ["device_01 safe limit 80"], ["device_01 status overheating"], [], 
                [{"action_type": "cool", "payload": {"device_id": "device_01"}}], 0.9
            ),
            "handler": action_success
        },
        {
            "name": "SCENARIO 2 — REVIEW",
            "decision": Decision(
                "Sum", "Rat", 
                [], [], [], 
                [{"action_type": "cool", "payload": {"device_id": "device_01"}}], 0.8, requires_deep_analysis=True
            ),
            "handler": action_success
        },
        {
            "name": "SCENARIO 3 — BLOCKED",
            "decision": Decision(
                "Sum", "Rat", 
                ["Hallucination"], [], [], 
                [{"action_type": "cool", "payload": {"device_id": "device_01"}}], 0.9
            ),
            "handler": action_success
        },
        {
            "name": "SCENARIO 4 — ACTION FAILURE",
            "decision": Decision(
                "Sum", "Rat", 
                ["device_01 safe limit 80"], ["device_01 status overheating"], [], 
                [{"action_type": "cool", "payload": {"device_id": "device_01"}}], 0.9
            ),
            "handler": action_fail
        }
    ]

    for sc in scenarios:
        print(f"==================================================")
        print(sc["name"])
        print(f"==================================================\n")

        # Initialize Runtime per scenario to maintain isolated state
        config = ATLASConfiguration()
        runtime = ATLASRuntime(primary_reasoner=FakeReasoner(sc["decision"]), configuration=config)
        
        # Pre-seed memory for Grounding validation to pass if observations match
        runtime.memory_manager.remember_fact("device_01", "device", "safe limit", "80")
        runtime.memory_manager.remember_fact("device_01", "device", "status", "overheating")
        
        runtime.register_action("cool", sc["handler"])
        
        print("[1] EVENT RECEIVED")
        print("[2] CONTEXT BUILT")
        
        # Process 
        result = runtime.process_event("sensor", {"device_id": "device_01"})
        
        print("[3] REASONING COMPLETE")
        print("[4] ARBITRATION RESULT")
        reasoning = result["reasoning_result"]
        print("Verdict:", reasoning.arbitration_result.verdict)
        
        print("[5] ACTION EXECUTION")
        exec_res = result["action_execution_result"]
        print("Skipped:", exec_res.skipped)
        if not exec_res.skipped:
            print("Executed:", [r.action_type for r in exec_res.executed_actions])
            print("Failed:", [r.action_type for r in exec_res.failed_actions])
            
        print("[6] EXECUTION FEEDBACK")
        fb = result["execution_feedback_result"]
        print("Processed Actions:", fb.processed_actions)
        print("Successful Actions:", fb.successful_actions)
        print("Failed Actions:", fb.failed_actions)
        print("Skipped:", fb.skipped)
        
        print("[7] FINAL SYSTEM STATE")
        ws = runtime.world_state
        print("Last Execution Batch in WorldState:")
        print_json(ws.last_execution_batch)
        print("\n")

if __name__ == "__main__":
    main()
