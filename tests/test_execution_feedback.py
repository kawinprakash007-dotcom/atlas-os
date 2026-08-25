import pytest
import tempfile
import os
import copy
from unittest.mock import MagicMock

from atlas_core.feedback import ExecutionFeedbackResult
from atlas_core.feedback.processor import ExecutionFeedbackProcessor
from atlas_core.actions.executor import ActionExecutionResult
from atlas_core.actions.dispatcher import ActionExecutionResult as DispatcherResult
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.events.gateway import EventGateway
from atlas_core.reasoning.pipeline import ATLASReasoningResult
from atlas_core.reasoning.arbitration import ArbitrationResult

@pytest.fixture
def memory_manager():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    store = SQLiteMemoryStore(path)
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    manager = MemoryManager(episodic, knowledge)
    
    yield manager
    
    try:
        os.remove(path)
    except OSError:
        pass

@pytest.fixture
def world_state():
    return WorldState()

@pytest.fixture
def event_history():
    return EventHistory()

@pytest.fixture
def processor(world_state, event_history, memory_manager):
    return ExecutionFeedbackProcessor(world_state, event_history, memory_manager)

def test_successful_action_updates(processor, world_state, event_history, memory_manager):
    event = Event("test", "test", "normal", {"id": "1"})
    result = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[DispatcherResult("action1", "SUCCESS", {"done": True})],
        blocked_actions=[],
        failed_actions=[],
        skipped=False
    )
    
    feedback = processor.process(result, event)
    
    assert feedback.skipped is False
    assert feedback.processed_actions == 1
    assert feedback.successful_actions == 1
    assert feedback.world_state_updated is True
    assert feedback.history_recorded is True
    assert feedback.memory_stored is True
    
    assert len(world_state.action_executions) == 1
    assert world_state.action_executions[0]["executed_actions"][0]["result"]["done"] is True
    
    events = event_history.get_recent()
    assert any(e.event_type == "action_execution_result" for e in events)

def test_failed_action_recorded_as_failed(processor, world_state):
    result = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[],
        blocked_actions=[],
        failed_actions=[DispatcherResult("action1", "FAILED", None, Exception("test error"))],
        skipped=False
    )
    
    feedback = processor.process(result)
    
    assert feedback.processed_actions == 1
    assert feedback.successful_actions == 0
    assert feedback.failed_actions == 1
    
    assert world_state.action_executions[0]["failed_actions"][0]["error"] == "test error"

def test_review_verdict_skipped(processor, world_state, event_history):
    result = ActionExecutionResult(
        verdict="REVIEW",
        executed_actions=[],
        blocked_actions=[{"action_type": "action1", "payload": {}}],
        failed_actions=[],
        skipped=True
    )
    
    feedback = processor.process(result)
    
    assert feedback.skipped is True
    assert feedback.processed_actions == 0
    assert len(world_state.action_executions) == 0
    assert len(event_history.get_recent()) == 0

def test_blocked_verdict_skipped(processor, world_state, event_history):
    result = ActionExecutionResult(
        verdict="BLOCKED",
        executed_actions=[],
        blocked_actions=[{"action_type": "action1", "payload": {}}],
        failed_actions=[],
        skipped=True
    )
    
    feedback = processor.process(result)
    
    assert feedback.skipped is True
    assert feedback.processed_actions == 0
    assert len(world_state.action_executions) == 0

def test_memory_failure_does_not_crash(processor):
    processor.memory_manager = MagicMock()
    processor.memory_manager.remember_event.side_effect = Exception("Memory Error")
    
    result = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[DispatcherResult("action1", "SUCCESS", {})],
        blocked_actions=[],
        failed_actions=[],
        skipped=False
    )
    
    feedback = processor.process(result)
    
    assert feedback.memory_stored is False
    assert feedback.world_state_updated is True
    assert feedback.history_recorded is True
    assert len(feedback.errors) == 1
    assert "Memory Error" in feedback.errors[0]

def test_immutability(processor):
    event = Event("test", "test", "normal", {"id": "1"})
    event_copy = copy.deepcopy(event)
    
    result = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[DispatcherResult("action1", "SUCCESS", {"done": True})],
        blocked_actions=[],
        failed_actions=[],
        skipped=False
    )
    result_copy = copy.deepcopy(result)
    
    processor.process(result, event)
    
    assert event.payload == event_copy.payload
    assert result.executed_actions == result_copy.executed_actions

def test_no_memory_manager_works(world_state, event_history):
    proc = ExecutionFeedbackProcessor(world_state, event_history, None)
    
    result = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[DispatcherResult("action1", "SUCCESS", {})],
        blocked_actions=[],
        failed_actions=[],
        skipped=False
    )
    
    feedback = proc.process(result)
    assert feedback.world_state_updated is True
    assert feedback.memory_stored is False
    assert len(feedback.errors) == 0

def test_full_gateway_integration(world_state, event_history, processor):
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
        arbitration_result=ArbitrationResult(
            verdict="APPROVED",
            approved=True, blocked=False, requires_human_review=False,
            allowed_actions=[{"action_type": "test", "payload": {}}],
            blocked_actions=[], reasons=[], confidence=1.0, grounding_status="TRUSTED", source="test"
        )
    )
    
    executor = MagicMock()
    executor.execute.return_value = ActionExecutionResult(
        verdict="APPROVED",
        executed_actions=[DispatcherResult("test", "SUCCESS", {})],
        blocked_actions=[], failed_actions=[], skipped=False
    )
    
    cb = MagicMock()
    cb.build_context.return_value = {"entities": {}}
    
    gw = EventGateway(world_state, event_history, cb, None, pipeline, executor, processor)
    event = Event("test", "test", "normal", {})
    
    res = gw.process(event)
    
    assert "execution_feedback_result" in res
    assert res["execution_feedback_result"].processed_actions == 1
    assert res["execution_feedback_result"].world_state_updated is True

def test_gateway_without_feedback_remains_compat(world_state):
    gw = EventGateway(world_state)
    event = Event("test", "test", "normal", {})
    res = gw.process(event)
    if res is not None:
        assert "execution_feedback_result" not in res
