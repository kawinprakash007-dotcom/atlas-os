from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.grounding import GroundingReport

@dataclass
class ArbitrationResult:
    verdict: str
    approved: bool
    blocked: bool
    requires_human_review: bool
    
    allowed_actions: List[Dict[str, Any]]
    blocked_actions: List[Dict[str, Any]]
    
    reasons: List[str]
    confidence: float
    grounding_status: str
    source: str

class DecisionArbiter:
    def _validate_actions(self, actions: List[Any]) -> bool:
        if not isinstance(actions, list):
            return False
            
        for action in actions:
            if not isinstance(action, dict):
                return False
            if "action_type" not in action or not isinstance(action["action_type"], str) or not action["action_type"].strip():
                return False
            if "payload" not in action or not isinstance(action["payload"], dict):
                return False
        return True

    def arbitrate(
        self,
        primary_decision: Decision,
        primary_grounding_report: GroundingReport,
        escalation_decision: Optional[Decision] = None,
        escalation_grounding_report: Optional[GroundingReport] = None
    ) -> ArbitrationResult:
        
        # 1. Select the candidate
        if escalation_decision is not None and escalation_grounding_report is not None:
            candidate_decision = escalation_decision
            candidate_grounding = escalation_grounding_report
            source = "escalation"
        else:
            candidate_decision = primary_decision
            candidate_grounding = primary_grounding_report
            source = "primary"
            
        reasons = []
        
        # 2. Extract values for logic
        status = candidate_grounding.status
        total_claims = (
            len(candidate_grounding.supported_claims) + 
            len(candidate_grounding.uncertain_claims) + 
            len(candidate_grounding.unsupported_claims)
        )
        unsupported_count = len(candidate_grounding.unsupported_claims)
        more_than_half_unsupported = False
        if total_claims > 0:
            if unsupported_count > (total_claims / 2.0):
                more_than_half_unsupported = True
                
        actions = candidate_decision.recommended_actions
        actions_valid = self._validate_actions(actions)
        
        # 3. Determine Verdict
        verdict = "REVIEW"
        
        # BLOCKED Logic
        if not actions_valid:
            reasons.append("Actions failed structural validation.")
            verdict = "BLOCKED"
            
        if status == "REJECTED":
            reasons.append("Grounding status is REJECTED.")
            verdict = "BLOCKED"
            
        if more_than_half_unsupported:
            reasons.append(f"Too many unsupported claims ({unsupported_count} out of {total_claims}).")
            verdict = "BLOCKED"
            
        # APPROVED Logic
        if verdict != "BLOCKED":
            if (
                status == "TRUSTED" and 
                unsupported_count == 0 and 
                candidate_decision.confidence >= 0.80 and 
                not candidate_decision.requires_deep_analysis and 
                actions_valid
            ):
                verdict = "APPROVED"
                reasons.append("All conditions met for automated approval.")
            else:
                verdict = "REVIEW"
                if status != "TRUSTED":
                    reasons.append(f"Grounding status is {status}, not TRUSTED.")
                if unsupported_count > 0:
                    reasons.append(f"There are {unsupported_count} unsupported claims.")
                if candidate_decision.confidence < 0.80:
                    reasons.append(f"Confidence {candidate_decision.confidence} is below 0.80 threshold.")
                if candidate_decision.requires_deep_analysis:
                    reasons.append("Decision requires deep analysis.")
                    
        # 4. Route Actions
        allowed_actions = []
        blocked_actions = []
        
        if verdict == "APPROVED":
            allowed_actions = list(actions)
        else:
            # BLOCKED and REVIEW both place actions in blocked_actions
            blocked_actions = list(actions)
            
        # 5. Build Result
        return ArbitrationResult(
            verdict=verdict,
            approved=(verdict == "APPROVED"),
            blocked=(verdict == "BLOCKED"),
            requires_human_review=(verdict == "REVIEW"),
            allowed_actions=allowed_actions,
            blocked_actions=blocked_actions,
            reasons=reasons,
            confidence=candidate_decision.confidence,
            grounding_status=status,
            source=source
        )
