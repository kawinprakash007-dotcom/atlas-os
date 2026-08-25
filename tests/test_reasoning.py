import pytest
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

def test_decision_creation_and_serialization():
    decision = Decision(
        situation_summary="Test Summary",
        observations=["Obs1"],
        inferences=["Inf1"],
        risks=["Risk1"],
        recommended_actions=[{"action_type": "test", "payload": {}}],
        confidence=0.8,
        requires_deep_analysis=True,
        decision_rationale="Because test."
    )
    
    assert decision.situation_summary == "Test Summary"
    assert decision.decision_rationale == "Because test."
    
    # Test serialization
    data = decision.to_dict()
    assert isinstance(data, dict)
    assert data["situation_summary"] == "Test Summary"
    assert data["confidence"] == 0.8
    assert data["requires_deep_analysis"] is True
    assert data["decision_rationale"] == "Because test."

def test_memory_retriever_read_only(tmp_path):
    # Setup mock memory manager
    db_path = tmp_path / "test_memory.db"
    store = SQLiteMemoryStore(str(db_path))
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    memory_manager = MemoryManager(episodic, knowledge)
    
    retriever = MemoryRetriever(memory_manager)
    
    # Pre-populate some knowledge
    memory_manager.remember_fact("test_d1", "device", "status", "online")
    
    situation_context = {
        "event_type": "test_event",
        "entities": {
            "device_id": ["test_d1"]
        }
    }
    
    result = retriever.retrieve(situation_context)
    
    assert "relevant_episodes" in result
    assert "relevant_knowledge" in result
    assert "test_d1" in result["relevant_knowledge"]
    assert len(result["relevant_knowledge"]["test_d1"]) == 1
    assert result["relevant_knowledge"]["test_d1"][0]["key"] == "status"

def test_fake_reasoner_deterministic_behavior():
    reasoner = FakeReasoner()
    
    situation_context = {}
    retrieved_memory = {}
    
    decision = reasoner.reason(situation_context, retrieved_memory)
    
    assert isinstance(decision, Decision)
    assert decision.situation_summary == "Deterministic test situation."
    assert decision.confidence == 0.9
    assert decision.decision_rationale == "Deterministic reasoning based on test situation."

def test_decision_validator_valid():
    validator = DecisionValidator()
    decision = Decision(
        observations=["A"],
        inferences=["B"],
        risks=["C"],
        recommended_actions=[{"action_type": "move", "payload": {"x": 1}}],
        confidence=0.5
    )
    result = validator.validate(decision)
    assert result["is_valid"] is True
    assert len(result["errors"]) == 0

def test_decision_validator_invalid_actions():
    validator = DecisionValidator()
    
    # Missing action_type
    decision = Decision(recommended_actions=[{"payload": {}}])
    res = validator.validate(decision)
    assert res["is_valid"] is False
    
    # Empty action_type
    decision = Decision(recommended_actions=[{"action_type": "", "payload": {}}])
    res = validator.validate(decision)
    assert res["is_valid"] is False
    
    # Missing payload
    decision = Decision(recommended_actions=[{"action_type": "move"}])
    res = validator.validate(decision)
    assert res["is_valid"] is False
    
    # Non-dict payload
    decision = Decision(recommended_actions=[{"action_type": "move", "payload": "string"}])
    res = validator.validate(decision)
    assert res["is_valid"] is False
    
    # Non-dict action
    decision = Decision(recommended_actions=["move"])
    res = validator.validate(decision)
    assert res["is_valid"] is False

def test_decision_validator_invalid():
    validator = DecisionValidator()
    decision = Decision()
    decision.confidence = 1.5 # Invalid confidence
    decision.observations = "Not a list" # Invalid type
    
    result = validator.validate(decision)
    assert result["is_valid"] is False
    assert len(result["errors"]) >= 2

def test_integration_flow(tmp_path):
    # Setup
    situation_context = {"event_type": "integration_test"}
    
    # Mock Memory Retriever
    db_path = tmp_path / "test_integration.db"
    store = SQLiteMemoryStore(str(db_path))
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    memory_manager = MemoryManager(episodic, knowledge)
    retriever = MemoryRetriever(memory_manager)
    
    # Retriever
    retrieved_memory = retriever.retrieve(situation_context, entity_ids=["test"])
    
    # Reasoner
    reasoner = FakeReasoner()
    decision = reasoner.reason(situation_context, retrieved_memory)
    
    # Validator
    validator = DecisionValidator()
    validation_result = validator.validate(decision)
    
    assert isinstance(decision, Decision)
    assert validation_result["is_valid"] is True
