import dataclasses
from typing import List, Dict, Any, Tuple
import re

from atlas_core.reasoning.decision import Decision

@dataclasses.dataclass
class GroundingReport:
    supported_claims: List[str]
    uncertain_claims: List[str]
    unsupported_claims: List[str]
    grounding_score: float
    status: str
    action_review: List[Dict[str, str]]

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

class GroundingValidator:
    def __init__(self):
        # Determine strict bidirectional contradictions
        self.contradictions = {
            "offline": "online",
            "online": "offline",
            "active": "inactive",
            "inactive": "active",
            "open": "closed",
            "closed": "open",
            "enabled": "disabled",
            "disabled": "enabled",
            "true": "false",
            "false": "true",
            "detected": "not_detected",
            "not_detected": "detected"
        }
        
        self.uncertainty_keywords = {"may", "might", "could", "possible", "potentially", "potential"}
        self.stop_words = {"a", "an", "the", "is", "are", "was", "were", "in", "at", "on", "of", "to", "for", "and"}

    def _normalize(self, text: str) -> set:
        # Lowercase and split into words
        tokens = set(re.findall(r'\b\w+\b', text.lower()))
        return tokens - self.stop_words

    def _check_contradiction(self, claim_tokens: set, evidence_tokens: set) -> bool:
        # If the evidence has one side of a contradiction pair, and the claim has the other
        for ev_token in evidence_tokens:
            if ev_token in self.contradictions:
                opposite = self.contradictions[ev_token]
                if opposite in claim_tokens:
                    shared_context = claim_tokens.intersection(evidence_tokens) - {ev_token, opposite}
                    if shared_context:
                        return True
        return False

    def _evaluate_claim(self, claim: str, evidence: List[str], claim_type: str) -> str:
        claim_tokens = self._normalize(claim)
        
        if not claim_tokens:
            return "unsupported"

        best_overlap = 0
        contradicted = False
        
        for ev in evidence:
            ev_tokens = self._normalize(ev)
            if not ev_tokens:
                continue
                
            # 1. Contradiction check
            if self._check_contradiction(claim_tokens, ev_tokens):
                contradicted = True
                continue
                
            # 2. Meaningful token overlap check
            overlap = len(claim_tokens.intersection(ev_tokens))
            if overlap > best_overlap:
                best_overlap = overlap

        # Classification Logic
        has_uncertainty = any(kw in claim_tokens for kw in self.uncertainty_keywords)

        if contradicted:
            return "unsupported"

        # Meaningful overlap means >= 2 tokens shared (after stop words removal)
        if best_overlap >= 2:
            if claim_type in ["inference", "risk"] and has_uncertainty:
                return "uncertain"
            return "supported"

        # Weak overlap (at least 1 token) is enough for uncertain claims
        if best_overlap > 0:
            if claim_type in ["inference", "risk"] and has_uncertainty:
                return "uncertain"

        return "unsupported"

    def evaluate(self, decision: Decision, evidence: List[str]) -> GroundingReport:
        supported_claims = []
        uncertain_claims = []
        unsupported_claims = []
        
        # 1. Observations
        for obs in decision.observations:
            res = self._evaluate_claim(obs, evidence, "observation")
            if res == "supported":
                supported_claims.append(obs)
            else:
                unsupported_claims.append(obs) # Observations can't be uncertain

        # 2. Inferences
        for inf in decision.inferences:
            res = self._evaluate_claim(inf, evidence, "inference")
            if res == "supported":
                supported_claims.append(inf)
            elif res == "uncertain":
                uncertain_claims.append(inf)
            else:
                unsupported_claims.append(inf)

        # 3. Risks
        for risk in decision.risks:
            res = self._evaluate_claim(risk, evidence, "risk")
            if res == "supported":
                supported_claims.append(risk)
            elif res == "uncertain":
                uncertain_claims.append(risk)
            else:
                unsupported_claims.append(risk)

        # Grounding Score Calculation
        total = len(supported_claims) + len(uncertain_claims) + len(unsupported_claims)
        if total == 0:
            grounding_score = 1.0
        else:
            grounding_score = (len(supported_claims) + 0.5 * len(uncertain_claims)) / total

        # Status Evaluation
        status = "CAUTION"
        if total > 0 and len(unsupported_claims) > total / 2.0:
            status = "REJECTED"
        elif grounding_score >= 0.85 and len(unsupported_claims) == 0:
            status = "TRUSTED"
        elif grounding_score < 0.60 or len(unsupported_claims) >= 2:
            status = "REQUIRES_DEEP_ANALYSIS"

        # Action Review
        action_review = []
        for action in decision.recommended_actions:
            action_type = action.get("action_type", "unknown")
            if len(supported_claims) > 0 or grounding_score >= 0.60:
                action_review.append({
                    "action_type": action_type,
                    "status": "ALLOWED_FOR_REVIEW"
                })
            else:
                action_review.append({
                    "action_type": action_type,
                    "status": "INSUFFICIENT_EVIDENCE"
                })

        return GroundingReport(
            supported_claims=supported_claims,
            uncertain_claims=uncertain_claims,
            unsupported_claims=unsupported_claims,
            grounding_score=grounding_score,
            status=status,
            action_review=action_review
        )
