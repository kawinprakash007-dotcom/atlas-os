import pytest
import copy
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder
from atlas_core.events.gateway import EventGateway
from atlas_core.reasoning.pipeline import ReasoningPipeline, ATLASReasoningResult
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.arbitration import ArbitrationResult
from unittest.mock import MagicMock

class FakeReasoner:
    def __init__(self, decision):
        self.decision = decision
    def reason(self, context, memory):
        return self.decision

@pytest.fixture
def base_gateway():
    world_state = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    context_builder = ContextBuilder(world_state, history, extractor)
    return EventGateway(
        world_state=world_state,
        event_history=history,
        context_builder=context_builder
    )

@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock(spec=ReasoningPipeline)
    return pipeline

@pytest.fixture
def event():
    return Event(
        source="sensor_1",
        event_type="sensor_reading",
        priority="normal",
        payload={"temperature": 92}
    )

def test_gateway_without_pipeline(base_gateway, event):
    # Test 1: EventGateway without ReasoningPipeline
    result = base_gateway.process(event)
    
    assert "trigger_event" in result
    assert "reasoning_result" not in result

def test_gateway_with_pipeline(base_gateway, event, mock_pipeline):
    # Test 2: EventGateway with ReasoningPipeline
    base_gateway.reasoning_pipeline = mock_pipeline
    
    mock_result = MagicMock(spec=ATLASReasoningResult)
    mock_pipeline.execute.return_value = mock_result
    
    result = base_gateway.process(event)
    
    assert result["reasoning_result"] == mock_result
    mock_pipeline.execute.assert_called_once()

def _setup_pipeline_mock_verdict(verdict, allowed=None, blocked=None):
    pipeline = MagicMock(spec=ReasoningPipeline)
    res = MagicMock(spec=ATLASReasoningResult)
    arb = ArbitrationResult(
        verdict=verdict,
        approved=(verdict=="APPROVED"),
        blocked=(verdict=="BLOCKED"),
        requires_human_review=(verdict=="REVIEW"),
        allowed_actions=allowed or [],
        blocked_actions=blocked or [],
        reasons=["mock"],
        confidence=1.0,
        grounding_status="TRUSTED",
        source="mock"
    )
    res.arbitration_result = arb
    pipeline.execute.return_value = res
    return pipeline

def test_gateway_strong_evidence(base_gateway, event):
    # Test 3: Strong evidence -> APPROVED
    pipeline = _setup_pipeline_mock_verdict("APPROVED")
    base_gateway.reasoning_pipeline = pipeline
    
    result = base_gateway.process(event)
    assert result["reasoning_result"].arbitration_result.verdict == "APPROVED"

def test_gateway_ambiguous_event(base_gateway, event):
    # Test 4: Ambiguous event -> REVIEW
    pipeline = _setup_pipeline_mock_verdict("REVIEW")
    base_gateway.reasoning_pipeline = pipeline
    
    result = base_gateway.process(event)
    assert result["reasoning_result"].arbitration_result.verdict == "REVIEW"

def test_gateway_hallucination(base_gateway, event):
    # Test 5: Hallucinated claims -> BLOCKED
    pipeline = _setup_pipeline_mock_verdict("BLOCKED", blocked=[{"action_type": "shutdown"}])
    base_gateway.reasoning_pipeline = pipeline
    
    result = base_gateway.process(event)
    arb = result["reasoning_result"].arbitration_result
    assert arb.verdict == "BLOCKED"
    assert len(arb.allowed_actions) == 0
    assert len(arb.blocked_actions) > 0

def test_input_immutability(base_gateway, event):
    # Test 6: Input immutability
    pipeline = MagicMock(spec=ReasoningPipeline)
    pipeline.execute.side_effect = lambda ctx: ctx.setdefault("MUTATED", True)
    
    base_gateway.reasoning_pipeline = pipeline
    
    original_data = copy.deepcopy(event.payload)
    
    result = base_gateway.process(event)
    
    # Event should be unchanged
    assert event.payload == original_data
    # Context returned should not have the mutation
    assert "MUTATED" not in result
