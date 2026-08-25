import pytest
import copy
import tempfile
import os

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

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
def pipeline(memory_manager):
    reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline", "motion detected"],
        inferences=["device_01 may be offline"]
    ))
    retriever = MemoryRetriever(memory_manager)
    collector = EvidenceCollector()
    validator = GroundingValidator()
    
    return ReasoningPipeline(reasoner, retriever, collector, validator)

def test_full_pipeline_trusted(pipeline, memory_manager):
    # Setup data
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    situation_context = {
        "entities": {
            "device_id": ["device_01"]
        },
        "state_snapshot": {
            "sensors": {
                "motion": "detected"
            }
        }
    }
    orig_context = copy.deepcopy(situation_context)
    
    pipeline.reasoner.fixed_decision = Decision(
        observations=["device_01 is offline"], 
        inferences=["motion was detected"],
        confidence=0.9,
        recommended_actions=[{"action_type": "test", "payload": {}}]
    )
    
    result = pipeline.execute(situation_context)
    
    # 2. Valid ATLASReasoningResult
    assert result.primary_decision is not None
    assert result.primary_grounding_report is not None
    
    # 3. TRUSTED routing
    assert result.final_status == "TRUSTED"
    assert result.escalation_required is False
    assert result.action_review_required is True
    assert result.blocked is False
    
    # Arbitration Check
    assert result.arbitration_result is not None
    assert result.arbitration_result.verdict == "APPROVED"
    assert result.arbitration_result.source == "primary"
    
    # 8. Mutate checks
    assert situation_context == orig_context

def test_full_pipeline_caution(pipeline, memory_manager):
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    situation_context = {
        "entities": {"device_id": ["device_01"]},
        "motion": "detected"
    }
    
    pipeline.reasoner.fixed_decision = Decision(
        observations=["device_01 is offline"], 
        inferences=["the offline device may have failed"], # uncertain
        confidence=0.9,
        recommended_actions=[{"action_type": "test", "payload": {}}]
    )
    
    result = pipeline.execute(situation_context)
    
    # 4. CAUTION routing
    assert result.final_status == "CAUTION"
    assert result.escalation_required is False
    assert result.action_review_required is True
    assert result.blocked is False
    
    # Arbitration Check
    assert result.arbitration_result is not None
    assert result.arbitration_result.verdict == "REVIEW"

def test_full_pipeline_requires_deep_analysis(pipeline, memory_manager):
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    situation_context = {
        "entities": {"device_id": ["device_01"]}
    }
    
    pipeline.reasoner.fixed_decision = Decision(
        observations=["device_01 is offline", "device_01 is offline"], 
        inferences=["ghosts caused the issue", "aliens stole it"] # 2 supported, 2 unsupported -> not > 50%
    )
    
    result = pipeline.execute(situation_context)
    
    # 5. REQUIRES_DEEP_ANALYSIS routing
    assert result.final_status == "REQUIRES_DEEP_ANALYSIS"
    assert result.escalation_required is True
    assert result.action_review_required is False
    assert result.blocked is False

def test_full_pipeline_rejected(pipeline, memory_manager):
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    situation_context = {
        "entities": {"device_id": ["device_01"]}
    }
    
    pipeline.reasoner.fixed_decision = Decision(
        inferences=["ghosts caused the issue", "aliens stole it", "demon activity"], # 3 unsupported
        confidence=0.9,
        recommended_actions=[{"action_type": "test", "payload": {}}]
    )
    
    result = pipeline.execute(situation_context)
    
    # 6. REJECTED routing
    assert result.final_status == "REJECTED"
    assert result.escalation_required is False
    assert result.action_review_required is False
    assert result.blocked is True
    
    # Arbitration Check
    assert result.arbitration_result is not None
    assert result.arbitration_result.verdict == "BLOCKED"

def test_grounding_improved_matching_and_contradiction():
    # 10. Meaningful overlap matches: "device_01 status offline" vs "device_01 is offline"
    # "is" is a stop word, remaining: "device_01", "offline" -> overlap 2 -> supported!
    validator = GroundingValidator()
    
    # Match
    decision = Decision(observations=["device_01 is offline"])
    evidence = ["device_01 status offline"]
    report = validator.evaluate(decision, evidence)
    assert len(report.supported_claims) == 1
    
    # 11. Contradiction rejects
    decision_contra = Decision(observations=["device_01 is online"])
    report_contra = validator.evaluate(decision_contra, evidence)
    assert len(report_contra.unsupported_claims) == 1
    assert len(report_contra.supported_claims) == 0
    
    # Generic word does NOT automatically become supported
    decision_generic = Decision(observations=["device is broken"])
    report_generic = validator.evaluate(decision_generic, evidence)
    assert len(report_generic.unsupported_claims) == 1

def test_pipeline_escalation_arbitration(pipeline, memory_manager):
    from atlas_core.reasoning.escalation import EscalationManager
    
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    situation_context = {"entities": {"device_id": ["device_01"]}}
    
    # Primary will return REQUIRES_DEEP_ANALYSIS (mixed support)
    pipeline.reasoner.fixed_decision = Decision(
        observations=["device_01 is offline", "device_01 is offline"], 
        inferences=["ghosts caused the issue", "aliens stole it"] 
    )
    
    # Escalation reasoner will return TRUSTED and APPROVED
    escalation_reasoner = FakeReasoner(Decision(
        observations=["device_01 is offline"],
        inferences=["device_01 is offline"],
        confidence=0.9,
        recommended_actions=[{"action_type": "test", "payload": {}}]
    ))
    
    pipeline.escalation_manager = EscalationManager(
        escalation_reasoner,
        None,  # decision_validator will be overridden
        pipeline.evidence_collector,
        pipeline.grounding_validator
    )
    from atlas_core.reasoning.validator import DecisionValidator
    pipeline.escalation_manager.decision_validator = DecisionValidator()
    
    result = pipeline.execute(situation_context)
    
    assert result.escalated is True
    assert result.arbitration_result is not None
    assert result.arbitration_result.source == "escalation"
    assert result.arbitration_result.verdict == "APPROVED"
