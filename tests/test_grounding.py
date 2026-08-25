import copy
import pytest
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator, GroundingReport

def test_evidence_extraction():
    collector = EvidenceCollector()
    
    situation_context = {
        "entities": {
            "device_id": ["device_01"]
        },
        "state_snapshot": {
            "active_devices": [],
            "sensors": {
                "motion": "detected"
            }
        }
    }

    retrieved_memory = {
        "knowledge": [
            {
                "entity_id": "device_01",
                "entity_type": "device",
                "key": "location",
                "value": "Main Lab"
            },
            {
                "entity_id": "device_01",
                "entity_type": "device",
                "key": "status",
                "value": "offline"
            }
        ],
        "episodes": []
    }
    
    orig_context = copy.deepcopy(situation_context)
    orig_memory = copy.deepcopy(retrieved_memory)

    evidence = collector.collect(situation_context, retrieved_memory)
    
    # 4. Input immutability
    assert situation_context == orig_context
    assert retrieved_memory == orig_memory
    
    # 1. Evidence extraction from situation_context
    assert "device_01" in evidence
    assert "motion detected" in evidence
    
    # 2. Evidence extraction from retrieved_memory
    assert "device_01 location Main Lab" in evidence
    assert "device_01 status offline" in evidence
    
    # 3. Duplicate evidence removal
    retrieved_memory["knowledge"].append({
        "entity_id": "device_01",
        "entity_type": "device",
        "key": "status",
        "value": "offline"
    })
    evidence_with_dup = collector.collect(situation_context, retrieved_memory)
    assert len(evidence_with_dup) == len(evidence)

def test_grounding_claim_classification():
    validator = GroundingValidator()
    
    evidence = [
        "device_01 location Main Lab",
        "device_01 status offline",
        "motion detected"
    ]
    
    decision = Decision()
    
    # 5. A directly supported observation
    decision.observations = ["device_01 status offline"]
    
    # 6. An uncertain inference containing words like may/might/could
    decision.inferences = ["The offline device may indicate a system failure."]
    
    # 7. An unsupported strong claim
    decision.risks = ["Someone definitely sabotaged device_01."]
    
    report = validator.evaluate(decision, evidence)
    
    assert "device_01 status offline" in report.supported_claims
    assert "The offline device may indicate a system failure." in report.uncertain_claims
    assert "Someone definitely sabotaged device_01." in report.unsupported_claims

def test_contradiction_detection():
    validator = GroundingValidator()
    evidence = ["device_01 status offline"]
    decision = Decision(observations=["device_01 is online"])
    
    # 8. Contradiction detection
    report = validator.evaluate(decision, evidence)
    assert "device_01 is online" in report.unsupported_claims
    assert len(report.supported_claims) == 0

def test_grounding_score_and_status():
    validator = GroundingValidator()
    evidence = ["device_01 status offline", "motion detected"]
    
    # 10. TRUSTED status
    trusted_decision = Decision(observations=["motion detected"], inferences=["device_01 status offline"])
    report = validator.evaluate(trusted_decision, evidence)
    assert report.grounding_score == 1.0
    assert report.status == "TRUSTED"
    
    # 11. CAUTION status
    caution_decision = Decision(
        observations=["motion detected"], 
        inferences=["device_01 may be offline"] # uncertain -> 0.5 points
    )
    report = validator.evaluate(caution_decision, evidence)
    assert report.grounding_score == 0.75 # (1 + 0.5) / 2
    assert report.status == "CAUTION"
    
    # 12. REQUIRES_DEEP_ANALYSIS status
    analysis_decision = Decision(
        observations=["motion detected", "device_01 status offline"], 
        inferences=["alien activity", "ghost activity"] # 2 supported, 2 unsupported. total=4. > 50% rule fails, but >= 2 rule hits!
    )
    report = validator.evaluate(analysis_decision, evidence)
    assert report.status == "REQUIRES_DEEP_ANALYSIS"
    
    # 13. REJECTED status
    rejected_decision = Decision(
        observations=["motion detected"], 
        inferences=["alien activity", "ghost activity", "demon activity"] # 3 unsupported out of 4 -> > 50%
    )
    report = validator.evaluate(rejected_decision, evidence)
    assert report.status == "REJECTED"

def test_action_review():
    validator = GroundingValidator()
    evidence = ["device_01 status offline"]
    
    # 14. Action review with sufficient evidence (supported claim present)
    decision1 = Decision(
        observations=["device_01 status offline"],
        recommended_actions=[{"action_type": "restart_device"}]
    )
    report1 = validator.evaluate(decision1, evidence)
    assert report1.action_review[0]["status"] == "ALLOWED_FOR_REVIEW"
    
    # 15. Action review with insufficient evidence
    decision2 = Decision(
        observations=["device_01 is online"], # Contradicted -> unsupported
        recommended_actions=[{"action_type": "restart_device"}]
    )
    report2 = validator.evaluate(decision2, evidence)
    assert report2.action_review[0]["status"] == "INSUFFICIENT_EVIDENCE"

def test_empty_decision_claims():
    validator = GroundingValidator()
    decision = Decision()
    
    # 16. Empty decision claims behavior
    report = validator.evaluate(decision, [])
    assert report.grounding_score == 1.0
    assert report.status == "TRUSTED" # No unsupported claims, score 1.0 >= 0.85
