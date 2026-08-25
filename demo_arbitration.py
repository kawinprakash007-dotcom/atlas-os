import dataclasses
import json
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.grounding import GroundingReport
from atlas_core.reasoning.arbitration import DecisionArbiter

def print_result(scenario: str, result):
    print(f"\n==================================================")
    print(f"SCENARIO: {scenario}")
    print(f"==================================================")
    print(f"Verdict: {result.verdict}")
    print(f"Approved: {result.approved}")
    print(f"Blocked: {result.blocked}")
    print(f"Requires Human Review: {result.requires_human_review}")
    print(f"\nAllowed Actions: {json.dumps(result.allowed_actions, indent=2)}")
    print(f"Blocked Actions: {json.dumps(result.blocked_actions, indent=2)}")
    if result.reasons:
        print(f"\nReasons:")
        for r in result.reasons:
            print(f" - {r}")
    print("==================================================\n")

def main():
    print("ATLAS Core v1.0 — Decision Arbitration Demo\n")
    arbiter = DecisionArbiter()
    
    # SCENARIO 1: High confidence + trusted grounding -> APPROVED
    decision1 = Decision(
        confidence=0.95,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "patch_system", "payload": {"target": "device_01"}}]
    )
    report1 = GroundingReport(
        status="TRUSTED",
        supported_claims=["device_01 is vulnerable"],
        unsupported_claims=[],
        uncertain_claims=[],
        grounding_score=1.0
    )
    res1 = arbiter.arbitrate(decision1, report1)
    print_result("1. High confidence + trusted grounding", res1)
    
    # SCENARIO 2: Moderate confidence or caution grounding -> REVIEW
    decision2 = Decision(
        confidence=0.70,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "restart_system", "payload": {"target": "server_02"}}]
    )
    report2 = GroundingReport(
        status="CAUTION",
        supported_claims=["server_02 is slow"],
        unsupported_claims=[],
        uncertain_claims=["server_02 may crash soon"],
        grounding_score=0.5
    )
    res2 = arbiter.arbitrate(decision2, report2)
    print_result("2. Moderate confidence + caution grounding", res2)
    
    # SCENARIO 3: Rejected grounding -> BLOCKED
    decision3 = Decision(
        confidence=0.90,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "ban_user", "payload": {"user": "admin"}}]
    )
    report3 = GroundingReport(
        status="REJECTED",
        supported_claims=[],
        unsupported_claims=["admin is an alien"],
        uncertain_claims=[],
        grounding_score=0.0
    )
    res3 = arbiter.arbitrate(decision3, report3)
    print_result("3. Rejected grounding", res3)

if __name__ == "__main__":
    main()
