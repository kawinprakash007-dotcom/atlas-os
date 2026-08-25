import copy
import traceback
from dataclasses import asdict
from typing import Dict, Any

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.pipeline import ATLASReasoningResult

class EscalationManager:
    def __init__(
        self,
        escalation_reasoner: BaseReasoner,
        decision_validator: DecisionValidator,
        evidence_collector: EvidenceCollector,
        grounding_validator: GroundingValidator
    ):
        self.escalation_reasoner = escalation_reasoner
        self.decision_validator = decision_validator
        self.evidence_collector = evidence_collector
        self.grounding_validator = grounding_validator

    def escalate(
        self,
        situation_context: Dict[str, Any],
        retrieved_memory: Dict[str, Any],
        primary_result: ATLASReasoningResult
    ) -> ATLASReasoningResult:
        # Do not mutate input
        escalation_situation = copy.deepcopy(situation_context)
        safe_memory = copy.deepcopy(retrieved_memory)

        # Build escalation input
        escalation_situation["escalation_context"] = {
            "instructions": (
                "A primary reasoning system analyzed this situation but the result required deeper analysis.\n"
                "Independently re-evaluate the available information.\n"
                "You must:\n"
                "1. Examine the original situation.\n"
                "2. Examine retrieved memory.\n"
                "3. Review the primary decision critically.\n"
                "4. Review why grounding was insufficient or uncertain.\n"
                "5. Identify unsupported assumptions.\n"
                "6. Correct incorrect conclusions if necessary.\n"
                "7. Produce your own structured Decision.\n"
                "8. Do not blindly agree with the primary model.\n"
                "9. Do not invent facts.\n"
                "10. Do not mutate ATLAS state."
            ),
            "primary_decision": asdict(primary_result.primary_decision),
            "primary_grounding_report": asdict(primary_result.primary_grounding_report)
        }

        # Safe fallback initialization
        result = copy.deepcopy(primary_result)
        result.escalated = True
        
        try:
            # Call escalation reasoner
            escalation_decision = self.escalation_reasoner.reason(escalation_situation, safe_memory)
            
            # Validate decision
            is_valid, errors = self.decision_validator.validate(escalation_decision)
            if not is_valid:
                raise ValueError(f"Escalation decision invalid: {errors}")
            
            # Collect evidence (use original situation/memory logic, EvidenceCollector only reads)
            evidence = self.evidence_collector.collect(situation_context, safe_memory)
            
            # Grounding
            escalation_grounding = self.grounding_validator.evaluate(escalation_decision, evidence)
            
            # Update result with escalation info
            result.escalation_decision = escalation_decision
            result.escalation_grounding_report = escalation_grounding
            result.final_decision = escalation_decision
            result.final_grounding_report = escalation_grounding
            
            # Final Status Routing
            status = escalation_grounding.status
            if status == "TRUSTED":
                result.final_status = "TRUSTED"
                result.escalation_required = False
                result.action_review_required = True
                result.blocked = False
            elif status == "CAUTION":
                result.final_status = "CAUTION"
                result.escalation_required = False
                result.action_review_required = True
                result.blocked = False
            elif status == "REQUIRES_DEEP_ANALYSIS":
                result.final_status = "REQUIRES_DEEP_ANALYSIS"
                result.escalation_required = True
                result.action_review_required = False
                result.blocked = False
            else:
                result.final_status = "REJECTED"
                result.escalation_required = False
                result.action_review_required = False
                result.blocked = True

        except Exception as e:
            # Escalation failure safety
            result.escalation_error = f"{type(e).__name__}: {str(e)}"
            # Final status remains REQUIRES_DEEP_ANALYSIS
            result.final_status = "REQUIRES_DEEP_ANALYSIS"
            result.escalation_required = True
            result.action_review_required = False
            result.blocked = False

        return result
