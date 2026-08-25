import pytest
from unittest.mock import MagicMock
import copy

from atlas_core.events.event import Event
from atlas_core.events.gateway import EventGateway
from atlas_core.reasoning.pipeline import ATLASReasoningResult
from atlas_core.reasoning.arbitration import ArbitrationResult
from atlas_core.actions.registry import ActionRegistry
from atlas_core.actions.safety import ActionSafetyValidator
from atlas_core.actions.dispatcher import ActionDispatcher
from atlas_core.actions.executor import ActionExecutor, ActionExecutionResult

def dummy_handler(payload):
    return {"status": "success", "payload_received": payload}

def failing_handler(payload):
    raise ValueError("Handler failed")

@pytest.fixture
def registry():
    r = ActionRegistry()
    r.register("activate_cooling", ["device_id"], dummy_handler)
    r.register("failing_action", ["id"], failing_handler)
    r.register("no_handler", ["id"])
    return r

@pytest.fixture
def executor(registry):
    validator = ActionSafetyValidator(registry)
    dispatcher = ActionDispatcher(registry)
    return ActionExecutor(validator, dispatcher)

def _create_arbitration(verdict, allowed_actions):
    return ArbitrationResult(
        verdict=verdict,
        approved=(verdict=="APPROVED"),
        blocked=(verdict=="BLOCKED"),
        requires_human_review=(verdict=="REVIEW"),
        allowed_actions=allowed_actions,
        blocked_actions=[],
        reasons=[],
        confidence=1.0,
        grounding_status="TRUSTED",
        source="test"
    )

def test_review_verdict_executes_nothing(executor):
    arb = _create_arbitration("REVIEW", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    result = executor.execute(arb)
    
    assert result.verdict == "REVIEW"
    assert result.skipped is True
    assert len(result.executed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_blocked_verdict_executes_nothing(executor):
    arb = _create_arbitration("BLOCKED", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    result = executor.execute(arb)
    
    assert result.verdict == "BLOCKED"
    assert result.skipped is True
    assert len(result.executed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_approved_verdict_executes_successfully(executor):
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    result = executor.execute(arb)
    
    assert result.verdict == "APPROVED"
    assert result.skipped is False
    assert len(result.executed_actions) == 1
    assert result.executed_actions[0].status == "SUCCESS"
    assert len(result.blocked_actions) == 0
    assert len(result.failed_actions) == 0

def test_approved_verdict_multiple_actions(executor):
    arb = _create_arbitration("APPROVED", [
        {"action_type": "activate_cooling", "payload": {"device_id": "1"}},
        {"action_type": "activate_cooling", "payload": {"device_id": "2"}}
    ])
    result = executor.execute(arb)
    
    assert result.skipped is False
    assert len(result.executed_actions) == 2
    assert len(result.blocked_actions) == 0

def test_unknown_action_blocked(executor):
    arb = _create_arbitration("APPROVED", [{"action_type": "unknown", "payload": {}}])
    result = executor.execute(arb)
    
    assert result.skipped is True
    assert len(result.executed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_malformed_action_blocked(executor):
    arb = _create_arbitration("APPROVED", ["not a dict"])
    result = executor.execute(arb)
    
    assert result.skipped is True
    assert len(result.blocked_actions) == 1

def test_missing_payload_field_blocked(executor):
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {}}])
    result = executor.execute(arb)
    
    assert result.skipped is True
    assert len(result.blocked_actions) == 1

def test_handler_exception_failed(executor):
    arb = _create_arbitration("APPROVED", [{"action_type": "failing_action", "payload": {"id": "1"}}])
    result = executor.execute(arb)
    
    assert result.skipped is False
    assert len(result.failed_actions) == 1
    assert len(result.executed_actions) == 0

def test_one_failed_action_does_not_prevent_next(executor):
    arb = _create_arbitration("APPROVED", [
        {"action_type": "failing_action", "payload": {"id": "1"}},
        {"action_type": "activate_cooling", "payload": {"device_id": "2"}}
    ])
    result = executor.execute(arb)
    
    assert result.skipped is False
    assert len(result.failed_actions) == 1
    assert len(result.executed_actions) == 1

def test_original_arbitration_result_not_mutated(executor):
    orig_allowed = [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}]
    arb = _create_arbitration("APPROVED", orig_allowed)
    arb_copy = copy.deepcopy(arb)
    
    executor.execute(arb)
    
    assert arb.allowed_actions == arb_copy.allowed_actions

def test_original_action_payload_not_mutated():
    r = ActionRegistry()
    def mutate(p):
        p["mutated"] = True
        return p
    r.register("mutator", [], mutate)
    exec = ActionExecutor(ActionSafetyValidator(r), ActionDispatcher(r))
    
    payload = {"key": "value"}
    arb = _create_arbitration("APPROVED", [{"action_type": "mutator", "payload": payload}])
    
    exec.execute(arb)
    assert "mutated" not in payload

def test_gateway_without_executor_maintains_compat():
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    assert "action_execution_result" not in res

def test_gateway_with_pipeline_without_executor():
    pipeline = MagicMock()
    pipeline.execute.return_value = ATLASReasoningResult(
        primary_decision=MagicMock(),
        primary_grounding_report=MagicMock(),
        escalated=False,
        final_decision=MagicMock(),
        final_grounding_report=MagicMock(),
        final_status="TRUSTED",
        escalation_required=False,
        action_review_required=True,
        blocked=False,
        arbitration_result=_create_arbitration("APPROVED", [])
    )
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), reasoning_pipeline=pipeline, context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    assert "reasoning_result" in res
    assert "action_execution_result" not in res

def test_gateway_with_pipeline_and_executor(executor):
    pipeline = MagicMock()
    pipeline.execute.return_value = ATLASReasoningResult(
        primary_decision=MagicMock(),
        primary_grounding_report=MagicMock(),
        escalated=False,
        final_decision=MagicMock(),
        final_grounding_report=MagicMock(),
        final_status="TRUSTED",
        escalation_required=False,
        action_review_required=True,
        blocked=False,
        arbitration_result=_create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    )
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), reasoning_pipeline=pipeline, action_executor=executor, context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    
    assert "reasoning_result" in res
    assert "action_execution_result" in res
    assert res["action_execution_result"].verdict == "APPROVED"
    assert len(res["action_execution_result"].executed_actions) == 1

def test_review_result_through_full_gateway_pipeline(executor):
    pipeline = MagicMock()
    pipeline.execute.return_value = ATLASReasoningResult(
        primary_decision=MagicMock(),
        primary_grounding_report=MagicMock(),
        escalated=False,
        final_decision=MagicMock(),
        final_grounding_report=MagicMock(),
        final_status="CAUTION",
        escalation_required=False,
        action_review_required=True,
        blocked=False,
        arbitration_result=_create_arbitration("REVIEW", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    )
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), reasoning_pipeline=pipeline, action_executor=executor, context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    
    assert res["action_execution_result"].verdict == "REVIEW"
    assert res["action_execution_result"].skipped is True

def test_blocked_result_through_full_gateway_pipeline(executor):
    pipeline = MagicMock()
    pipeline.execute.return_value = ATLASReasoningResult(
        primary_decision=MagicMock(),
        primary_grounding_report=MagicMock(),
        escalated=False,
        final_decision=MagicMock(),
        final_grounding_report=MagicMock(),
        final_status="REJECTED",
        escalation_required=False,
        action_review_required=False,
        blocked=True,
        arbitration_result=_create_arbitration("BLOCKED", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    )
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), reasoning_pipeline=pipeline, action_executor=executor, context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    
    assert res["action_execution_result"].verdict == "BLOCKED"
    assert res["action_execution_result"].skipped is True

def test_approved_result_through_full_gateway_pipeline_executes(executor):
    pipeline = MagicMock()
    pipeline.execute.return_value = ATLASReasoningResult(
        primary_decision=MagicMock(),
        primary_grounding_report=MagicMock(),
        escalated=False,
        final_decision=MagicMock(),
        final_grounding_report=MagicMock(),
        final_status="TRUSTED",
        escalation_required=False,
        action_review_required=True,
        blocked=False,
        arbitration_result=_create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {"device_id": "1"}}])
    )
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    gw = EventGateway(world_state=MagicMock(), reasoning_pipeline=pipeline, action_executor=executor, context_builder=cb)
    event = Event(source="test", event_type="test", priority="normal", payload={})
    res = gw.process(event)
    
    assert res["action_execution_result"].verdict == "APPROVED"
    assert res["action_execution_result"].skipped is False
    assert len(res["action_execution_result"].executed_actions) == 1
