import pytest
import copy

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import FakeReasoner, BaseReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.reasoning.escalation import EscalationManager
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

class ThrowingReasoner(BaseReasoner):
    def reason(self, context, memory):
        raise ValueError("Model crashed!")

@pytest.fixture
def memory_manager():
    import tempfile
    import os
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
def base_components(memory_manager):
    retriever = MemoryRetriever(memory_manager)
    collector = EvidenceCollector()
    grounding_validator = GroundingValidator()
    decision_validator = DecisionValidator()
    return retriever, collector, grounding_validator, decision_validator

def test_no_escalation_manager(base_components, memory_manager):
    # 11. Backward compatibility (no escalation manager)
    retriever, collector, grounding_validator, decision_validator = base_components
    
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], 
        inferences=["motion was detected"]
    ))
    
    pipeline = ReasoningPipeline(
        reasoner=reasoner,
        retriever=retriever,
        evidence_collector=collector,
        grounding_validator=grounding_validator
    )
    
    context = {"entities": {"device_id": ["device_01"]}, "state_snapshot": {"sensors": {"motion": "detected"}}}
    result = pipeline.execute(context)
    
    assert result.escalated is False
    assert result.final_status == "TRUSTED"
    assert result.escalation_decision is None

def test_escalation_triggered(base_components, memory_manager):
    # 4. Escalation occurs when primary is REQUIRES_DEEP_ANALYSIS
    # 5. Primary REQUIRES_DEEP_ANALYSIS -> escalation TRUSTED
    retriever, collector, grounding_validator, decision_validator = base_components
    
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    # Primary will return unsupported inferences -> REQUIRES_DEEP_ANALYSIS
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], 
        inferences=["aliens stole it", "ghosts caused the issue"]
    ))
    
    # Escalation reasoner will return supported inferences -> TRUSTED
    escalation_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"],
        inferences=["motion was detected"]
    ))
    
    escalation_manager = EscalationManager(
        escalation_reasoner, decision_validator, collector, grounding_validator
    )
    
    pipeline = ReasoningPipeline(
        reasoner=primary_reasoner,
        retriever=retriever,
        evidence_collector=collector,
        grounding_validator=grounding_validator,
        escalation_manager=escalation_manager
    )
    
    context = {"entities": {"device_id": ["device_01"]}, "state_snapshot": {"sensors": {"motion": "detected"}}}
    orig_context = copy.deepcopy(context)
    result = pipeline.execute(context)
    
    assert result.escalated is True
    assert result.escalation_decision is not None
    assert result.final_status == "TRUSTED"
    assert result.escalation_required is False
    assert result.action_review_required is True
    assert result.blocked is False
    assert context == orig_context # 10. Read-only safety

def test_no_escalation_for_trusted(base_components, memory_manager):
    # 1. No escalation for TRUSTED
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"]
    ))
    escalation_reasoner = ThrowingReasoner() # Will fail if called
    
    escalation_manager = EscalationManager(
        escalation_reasoner, decision_validator, collector, grounding_validator
    )
    pipeline = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, escalation_manager)
    
    result = pipeline.execute({"entities": {"device_id": ["device_01"]}})
    assert result.final_status == "TRUSTED"
    assert result.escalated is False

def test_no_escalation_for_caution(base_components, memory_manager):
    # 2. No escalation for CAUTION
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"],
        inferences=["device may be broken"]
    ))
    escalation_reasoner = ThrowingReasoner() 
    
    escalation_manager = EscalationManager(escalation_reasoner, decision_validator, collector, grounding_validator)
    pipeline = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, escalation_manager)
    
    result = pipeline.execute({"entities": {"device_id": ["device_01"]}})
    assert result.final_status == "CAUTION"
    assert result.escalated is False

def test_no_escalation_for_rejected(base_components, memory_manager):
    # 3. No escalation for REJECTED
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        inferences=["aliens", "ghosts", "demons"]
    ))
    escalation_reasoner = ThrowingReasoner() 
    
    escalation_manager = EscalationManager(escalation_reasoner, decision_validator, collector, grounding_validator)
    pipeline = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, escalation_manager)
    
    result = pipeline.execute({"entities": {"device_id": ["device_01"]}})
    assert result.final_status == "REJECTED"
    assert result.escalated is False

def test_escalation_caution_and_rejected(base_components, memory_manager):
    # 6. Primary REQUIRES_DEEP_ANALYSIS -> escalation CAUTION
    # 8. Primary REQUIRES_DEEP_ANALYSIS -> escalation REJECTED
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], inferences=["aliens", "ghosts"]
    ))
    escalation_reasoner_caution = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], inferences=["device may be broken"]
    ))
    escalation_reasoner_rejected = FakeReasoner(Decision(
        inferences=["aliens", "ghosts", "demons"]
    ))
    
    ctx = {"entities": {"device_id": ["device_01"]}}
    
    # Caution test
    em_caution = EscalationManager(escalation_reasoner_caution, decision_validator, collector, grounding_validator)
    pipe_caution = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, em_caution)
    res1 = pipe_caution.execute(ctx)
    assert res1.escalated is True
    assert res1.final_status == "CAUTION"
    assert res1.action_review_required is True
    
    # Rejected test
    em_reject = EscalationManager(escalation_reasoner_rejected, decision_validator, collector, grounding_validator)
    pipe_reject = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, em_reject)
    res2 = pipe_reject.execute(ctx)
    assert res2.escalated is True
    assert res2.final_status == "REJECTED"
    assert res2.blocked is True

def test_escalation_requires_deep_analysis(base_components, memory_manager):
    # 7. Primary REQUIRES_DEEP_ANALYSIS -> escalation REQUIRES_DEEP_ANALYSIS
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], inferences=["aliens", "ghosts"]
    ))
    escalation_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], inferences=["aliens", "ghosts"]
    ))
    
    em = EscalationManager(escalation_reasoner, decision_validator, collector, grounding_validator)
    pipe = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, em)
    
    res = pipe.execute({"entities": {"device_id": ["device_01"]}})
    assert res.escalated is True
    assert res.final_status == "REQUIRES_DEEP_ANALYSIS"
    assert res.escalation_required is True # Still true, but won't loop because pipe only escalates once

def test_escalation_failure(base_components, memory_manager):
    # 9. Escalation failure
    retriever, collector, grounding_validator, decision_validator = base_components
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    primary_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "device_01 is offline"], inferences=["aliens", "ghosts"]
    ))
    escalation_reasoner = ThrowingReasoner()
    
    em = EscalationManager(escalation_reasoner, decision_validator, collector, grounding_validator)
    pipe = ReasoningPipeline(primary_reasoner, retriever, collector, grounding_validator, em)
    
    res = pipe.execute({"entities": {"device_id": ["device_01"]}})
    
    assert res.escalated is True
    assert res.escalation_error is not None
    assert "ValueError: Model crashed!" in res.escalation_error
    assert res.final_status == "REQUIRES_DEEP_ANALYSIS"
    assert res.escalation_required is True
    assert res.action_review_required is False
    assert res.blocked is False
