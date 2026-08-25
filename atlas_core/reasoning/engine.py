from typing import Dict, Any
from abc import ABC, abstractmethod
from atlas_core.reasoning.decision import Decision

class BaseReasoner(ABC):
    @abstractmethod
    def reason(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> Decision:
        """
        Generates a Decision based on current context and memory.
        Must be read-only with respect to WorldState and MemoryManager.
        """
        pass

class FakeReasoner(BaseReasoner):
    """
    A deterministic reasoner for automated testing and validation.
    Does not connect to any external LLM.
    """
    def __init__(self, fixed_decision: Decision = None):
        self.fixed_decision = fixed_decision

    def reason(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> Decision:
        if self.fixed_decision:
            return self.fixed_decision
            
        decision = Decision(
            situation_summary="Deterministic test situation.",
            observations=["Observation 1"],
            inferences=["Inference A"],
            risks=["Low risk"],
            recommended_actions=[{"action_type": "test_action", "payload": {}}],
            confidence=0.9,
            requires_deep_analysis=False,
            decision_rationale="Deterministic reasoning based on test situation."
        )
        return decision
