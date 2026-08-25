import pytest
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.grounding import GroundingReport
from atlas_core.reasoning.arbitration import DecisionArbiter

@pytest.fixture
def arbiter():
    return DecisionArbiter()

def test_trusted_high_confidence(arbiter):
    # 1. Trusted decision + confidence >= 0.80 -> APPROVED
    decision = Decision(
        confidence=0.85,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="TRUSTED",
        supported_claims=["claim1"],
        unsupported_claims=[],
        uncertain_claims=[],
        grounding_score=1.0,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "APPROVED"
    assert result.approved is True
    assert result.blocked is False
    assert result.requires_human_review is False
    assert len(result.allowed_actions) == 1
    assert len(result.blocked_actions) == 0

def test_trusted_low_confidence(arbiter):
    # 2. TRUSTED but confidence < 0.80 -> REVIEW
    decision = Decision(
        confidence=0.75,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="TRUSTED",
        supported_claims=["claim1"],
        unsupported_claims=[],
        uncertain_claims=[],
        grounding_score=1.0,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "REVIEW"
    assert result.requires_human_review is True
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_caution(arbiter):
    # 3. CAUTION -> REVIEW
    decision = Decision(
        confidence=0.90,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="CAUTION",
        supported_claims=["claim1"],
        unsupported_claims=[],
        uncertain_claims=["claim2"],
        grounding_score=0.5,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "REVIEW"

def test_requires_deep_analysis(arbiter):
    # 4. REQUIRES_DEEP_ANALYSIS -> REVIEW
    decision = Decision(
        confidence=0.90,
        requires_deep_analysis=True,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="TRUSTED",
        supported_claims=["claim1"],
        unsupported_claims=[],
        uncertain_claims=[],
        grounding_score=1.0,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "REVIEW"

def test_rejected(arbiter):
    # 5. REJECTED -> BLOCKED
    decision = Decision(
        confidence=0.90,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="REJECTED",
        supported_claims=[],
        unsupported_claims=["claim1"],
        uncertain_claims=[],
        grounding_score=0.0,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "BLOCKED"
    assert result.blocked is True
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_more_than_half_unsupported(arbiter):
    # 6. More than half unsupported claims -> BLOCKED
    decision = Decision(
        confidence=0.90,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(
        status="TRUSTED", # Even if marked trusted, logic overrides it
        supported_claims=["claim1"],
        unsupported_claims=["claim2", "claim3"],
        uncertain_claims=[],
        grounding_score=0.33,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "BLOCKED"

def test_malformed_action(arbiter):
    # 7. Malformed recommended action -> BLOCKED
    decision = Decision(
        confidence=0.90,
        requires_deep_analysis=False,
        recommended_actions=[{"action_type": "", "payload": {}}] # Invalid action type
    )
    report = GroundingReport(
        status="TRUSTED",
        supported_claims=["claim1"],
        unsupported_claims=[],
        uncertain_claims=[],
        grounding_score=1.0,
        action_review=[]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "BLOCKED"
    assert "Actions failed structural validation." in result.reasons

def test_escalation_priority(arbiter):
    # 8. Escalation result preferred over primary result
    primary_decision = Decision(confidence=0.1)
    primary_report = GroundingReport(status="REJECTED", supported_claims=[], unsupported_claims=[], uncertain_claims=[], grounding_score=0.0, action_review=[])
    
    escalation_decision = Decision(confidence=0.9, requires_deep_analysis=False, recommended_actions=[])
    escalation_report = GroundingReport(status="TRUSTED", supported_claims=["claim1"], unsupported_claims=[], uncertain_claims=[], grounding_score=1.0, action_review=[])
    
    result = arbiter.arbitrate(primary_decision, primary_report, escalation_decision, escalation_report)
    
    assert result.source == "escalation"
    assert result.verdict == "APPROVED"
    assert result.confidence == 0.9

def test_review_actions_routing(arbiter):
    # 9. REVIEW actions are NOT placed in allowed_actions
    decision = Decision(
        confidence=0.7,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(status="TRUSTED", supported_claims=["claim1"], unsupported_claims=[], uncertain_claims=[], grounding_score=1.0, action_review=[])
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "REVIEW"
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1
    assert result.blocked_actions[0]["action_type"] == "log"

def test_approved_actions_routing(arbiter):
    # 10. APPROVED actions are placed in allowed_actions
    decision = Decision(
        confidence=0.9,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(status="TRUSTED", supported_claims=["claim1"], unsupported_claims=[], uncertain_claims=[], grounding_score=1.0, action_review=[])
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "APPROVED"
    assert len(result.allowed_actions) == 1
    assert len(result.blocked_actions) == 0
    assert result.allowed_actions[0]["action_type"] == "log"

def test_blocked_actions_routing(arbiter):
    # 11. BLOCKED actions are placed in blocked_actions
    decision = Decision(
        confidence=0.9,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(status="REJECTED", supported_claims=[], unsupported_claims=["claim1"], uncertain_claims=[], grounding_score=0.0, action_review=[])
    
    result = arbiter.arbitrate(decision, report)
    
    assert result.verdict == "BLOCKED"
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1
    assert result.blocked_actions[0]["action_type"] == "log"

def test_immutability(arbiter):
    # 12. Input Decision and GroundingReport objects are not mutated
    decision = Decision(
        confidence=0.9,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    report = GroundingReport(status="TRUSTED", supported_claims=["claim1"], unsupported_claims=[], uncertain_claims=[], grounding_score=1.0, action_review=[])
    
    decision_copy = Decision(
        confidence=0.9,
        recommended_actions=[{"action_type": "log", "payload": {}}]
    )
    
    result = arbiter.arbitrate(decision, report)
    
    assert decision.confidence == decision_copy.confidence
    assert decision.recommended_actions == decision_copy.recommended_actions
    assert report.status == "TRUSTED"
