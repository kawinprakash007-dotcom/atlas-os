import copy
from typing import Dict, Any
from dataclasses import dataclass

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator, GroundingReport
from atlas_core.reasoning.arbitration import DecisionArbiter, ArbitrationResult


@dataclass
class ATLASReasoningResult:
    primary_decision: Decision
    primary_grounding_report: GroundingReport
    escalated: bool
    final_decision: Decision
    final_grounding_report: GroundingReport
    final_status: str
    escalation_required: bool
    action_review_required: bool
    blocked: bool
    escalation_decision: Decision = None
    escalation_grounding_report: GroundingReport = None
    escalation_error: str = None
    arbitration_result: ArbitrationResult = None


class ReasoningPipeline:
    def __init__(
        self,
        reasoner: BaseReasoner,
        retriever: MemoryRetriever,
        evidence_collector: EvidenceCollector,
        grounding_validator: GroundingValidator,
        escalation_manager=None
    ):
        self.reasoner = reasoner
        self.retriever = retriever
        self.evidence_collector = evidence_collector
        self.grounding_validator = grounding_validator
        self.escalation_manager = escalation_manager
        self.arbiter = DecisionArbiter()

    def _is_decision_incomplete(self, decision: Decision) -> bool:
        """
        Detect unusable or incomplete reasoning output.

        An empty decision must never be treated as trustworthy simply because
        there are no claims for the grounding layer to reject.
        """

        total_claims = (
            len(decision.observations)
            + len(decision.inferences)
            + len(decision.risks)
        )

        has_summary = bool(
            decision.situation_summary
            and decision.situation_summary.strip()
        )

        has_rationale = bool(
            decision.decision_rationale
            and decision.decision_rationale.strip()
        )

        return (
            total_claims == 0
            or decision.confidence <= 0.0
            or not has_summary
            or not has_rationale
        )

    def execute(
        self,
        situation_context: Dict[str, Any]
    ) -> ATLASReasoningResult:

        # Do not mutate caller input
        safe_context = copy.deepcopy(situation_context)

        # --------------------------------------------------
        # 1. Retrieve memory
        # --------------------------------------------------

        retrieved_memory = self.retriever.retrieve(
            safe_context
        )

        # --------------------------------------------------
        # 2. Primary reasoning
        # --------------------------------------------------

        primary_decision = self.reasoner.reason(
            safe_context,
            retrieved_memory
        )

        # --------------------------------------------------
        # 3. Collect evidence
        # --------------------------------------------------

        evidence = self.evidence_collector.collect(
            safe_context,
            retrieved_memory
        )

        # --------------------------------------------------
        # 4. Ground primary decision
        # --------------------------------------------------

        primary_grounding = self.grounding_validator.evaluate(
            primary_decision,
            evidence
        )

        # --------------------------------------------------
        # 5. Decision completeness safety check
        # --------------------------------------------------

        decision_incomplete = self._is_decision_incomplete(
            primary_decision
        )

        # --------------------------------------------------
        # 6. Primary routing
        # --------------------------------------------------

        status = primary_grounding.status

        if status == "TRUSTED":
            final_status = "TRUSTED"
            escalation_req = False
            action_req = True
            blocked = False
        elif status == "CAUTION":
            final_status = "CAUTION"
            escalation_req = False
            action_req = True
            blocked = False
        elif status == "REQUIRES_DEEP_ANALYSIS":
            final_status = "REQUIRES_DEEP_ANALYSIS"
            escalation_req = True
            action_req = False
            blocked = False
        elif status == "REJECTED":
            final_status = "REJECTED"
            escalation_req = False
            action_req = False
            blocked = True
        else:
            final_status = "REJECTED"
            escalation_req = False
            action_req = False
            blocked = True

        # Safety & explicit requests overrides
        if not blocked:
            if primary_decision.requires_deep_analysis:
                escalation_req = True
                action_req = False

        # --------------------------------------------------
        # 7. Build primary result
        # --------------------------------------------------

        result = ATLASReasoningResult(
            primary_decision=primary_decision,
            primary_grounding_report=primary_grounding,
            escalated=False,
            final_decision=primary_decision,
            final_grounding_report=primary_grounding,
            final_status=final_status,
            escalation_required=escalation_req,
            action_review_required=action_req,
            blocked=blocked
        )

        # --------------------------------------------------
        # 8. Escalation
        # --------------------------------------------------

        if (
            result.escalation_required
            and self.escalation_manager is not None
        ):

            result = self.escalation_manager.escalate(
                situation_context=safe_context,
                retrieved_memory=retrieved_memory,
                primary_result=result
            )

        # --------------------------------------------------
        # 9. Final decision arbitration
        # --------------------------------------------------

        arb_result = self.arbiter.arbitrate(
            primary_decision=result.primary_decision,
            primary_grounding_report=result.primary_grounding_report,
            escalation_decision=result.escalation_decision,
            escalation_grounding_report=result.escalation_grounding_report
        )

        result.arbitration_result = arb_result

        return result