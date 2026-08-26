from typing import Dict, Any
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.command_reasoner import CommandReasoner
from atlas_core.reasoning.llm_service import LLMService

class IntentRouter(BaseReasoner):
    def __init__(self, command_reasoner: CommandReasoner, llm_service: LLMService):
        self.command_reasoner = command_reasoner
        self.llm_service = llm_service
        
    def reason(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> Decision:
        # First, let CommandReasoner evaluate it (handles OS commands and safety)
        command_decision = self.command_reasoner.reason(situation_context, retrieved_memory)
        
        rationale = command_decision.decision_rationale
        
        # If it's a valid command (has recommended_actions) or it was explicitly rejected
        # for safety reasons ("outside the ATLAS safety policy"), we return it immediately.
        if command_decision.recommended_actions or "outside the ATLAS safety policy" in rationale:
            return command_decision
            
        # If CommandReasoner unsupported the command, it means it's a conversational intent.
        if "not currently enabled in ATLAS" in rationale:
            llm_decision = self.llm_service.reason(situation_context, retrieved_memory)
            if llm_decision:
                return llm_decision
                
            # Fallback if LLM fails/disabled
            return Decision(
                situation_summary="Conversational response fallback.",
                observations=command_decision.observations,
                inferences=["LLM Service unavailable."],
                risks=[],
                recommended_actions=[],
                confidence=1.0,
                requires_deep_analysis=False,
                decision_rationale="Advanced reasoning is currently unavailable, but I can still assist with supported ATLAS OS commands."
            )
            
        return command_decision
