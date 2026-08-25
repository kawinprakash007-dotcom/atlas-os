import pytest
import os
from typing import Dict, Any

from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.runtime.atlas_runtime import ATLASRuntime
from atlas_core.reasoning.decision import Decision

class FakeReasoner:
    def __init__(self, fixed_decision: Decision):
        self.fixed_decision = fixed_decision
    def reason(self, situation: Dict[str, Any], memory: Dict[str, Any]) -> Decision:
        return self.fixed_decision

def sample_action_handler(payload):
    return {"status": "success", "echo": payload}

def failing_action_handler(payload):
    raise RuntimeError("Intentional Failure")

def create_runtime(decision: Decision):
    reasoner = FakeReasoner(decision)
    # Use explicit memory path to avoid any global SQLite quirks during testing,
    # though runtime creates tempfile if not given.
    config = ATLASConfiguration()
    runtime = ATLASRuntime(primary_reasoner=reasoner, configuration=config)
    return runtime

def test_runtime_initialization():
    decision = Decision("Summary", "Rationale", [], [], [], [], 0.9)
    runtime = create_runtime(decision)
    
    assert runtime.world_state is not None
    assert runtime.event_history is not None
    assert runtime.event_gateway is not None
    assert runtime.reasoning_pipeline is not None
    assert runtime.action_executor is not None
    assert runtime.feedback_processor is not None

def test_approved_flow():
    decision = Decision(
        "Summary", "Rationale", 
        observations=["device_01 safe limit 80"],
        inferences=["device_01 status overheating"],
        risks=[],
        recommended_actions=[{"action_type": "cool", "payload": {"device_id": "device_01"}}], 
        confidence=0.9
    )
    runtime = create_runtime(decision)
    
    # Pre-load memory so grounding passes
    runtime.memory_manager.remember_fact("device_01", "device", "safe limit", "80")
    runtime.memory_manager.remember_fact("device_01", "device", "status", "overheating")
    
    runtime.register_action("cool", sample_action_handler)
    
    payload = {"device_id": "device_01", "temperature": 95}
    result = runtime.process_event("sensor", payload)
    
    assert "reasoning_result" in result
    assert result["reasoning_result"].arbitration_result.verdict == "APPROVED"
    assert "action_execution_result" in result
    assert len(result["action_execution_result"].executed_actions) == 1
    assert "execution_feedback_result" in result
    assert result["execution_feedback_result"].successful_actions == 1
    
    # Verify WorldState update
    assert len(runtime.world_state.action_executions) == 1
    assert runtime.world_state.action_executions[0]["executed_actions"][0]["action_type"] == "cool"

def test_review_flow():
    decision = Decision(
        "Summary", "Rationale", [], [], [], 
        recommended_actions=[{"action_type": "cool", "payload": {}}], 
        confidence=0.8,
        requires_deep_analysis=True
    )
    runtime = create_runtime(decision)
    runtime.register_action("cool", sample_action_handler)
    
    result = runtime.process_event("sensor", {"device_id": "device_01"})
    
    assert result["reasoning_result"].arbitration_result.verdict == "REVIEW"
    assert result["action_execution_result"].skipped is True
    assert result["execution_feedback_result"].processed_actions == 0
    assert len(runtime.world_state.action_executions) == 0

def test_blocked_flow():
    decision = Decision(
        "Summary", "Rationale", 
        observations=["Hallucinated observation"],
        inferences=[], risks=[], 
        recommended_actions=[{"action_type": "cool", "payload": {}}], 
        confidence=0.9
    )
    runtime = create_runtime(decision)
    runtime.register_action("cool", sample_action_handler)
    
    result = runtime.process_event("sensor", {"device_id": "device_01"})
    
    assert result["reasoning_result"].arbitration_result.verdict == "BLOCKED"
    assert result["action_execution_result"].skipped is True
    assert result["execution_feedback_result"].processed_actions == 0
    assert len(runtime.world_state.action_executions) == 0

def test_action_failure():
    decision = Decision(
        "Summary", "Rationale", 
        observations=["device_01 safe limit 80"],
        inferences=["device_01 status overheating"],
        risks=[],
        recommended_actions=[{"action_type": "break", "payload": {"device_id": "device_01"}}], 
        confidence=0.9
    )
    runtime = create_runtime(decision)
    
    runtime.memory_manager.remember_fact("device_01", "device", "safe limit", "80")
    runtime.memory_manager.remember_fact("device_01", "device", "status", "overheating")
    
    runtime.register_action("break", failing_action_handler)
    
    result = runtime.process_event("sensor", {"device_id": "device_01"})
    
    assert result["reasoning_result"].arbitration_result.verdict == "APPROVED"
    assert result["action_execution_result"].skipped is False
    assert len(result["action_execution_result"].failed_actions) == 1
    
    fb = result["execution_feedback_result"]
    assert fb.failed_actions == 1
    assert fb.successful_actions == 0
    
    # World state reflects failure
    ws_exec = runtime.world_state.action_executions[0]
    assert len(ws_exec["failed_actions"]) == 1
    assert "Intentional Failure" in ws_exec["failed_actions"][0]["error"]

def test_immutability():
    decision = Decision("Sum", "Rat", [], [], [], [], 0.9)
    runtime = create_runtime(decision)
    
    payload = {"device_id": "device_01", "nested": {"val": 1}}
    
    result = runtime.process_event("sensor", payload)
    
    assert payload == {"device_id": "device_01", "nested": {"val": 1}}
