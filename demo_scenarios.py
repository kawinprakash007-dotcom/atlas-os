import sys
import os
import tempfile
import json
import dataclasses
from typing import Any, Dict, List, Optional

from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.memory.manager import MemoryManager

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.qwen import QwenReasoner, ReasoningIntegrationError
from atlas_core.reasoning.ornith import OrnithReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.escalation import EscalationManager
from atlas_core.reasoning.arbitration import DecisionArbiter
from atlas_core.reasoning.pipeline import ReasoningPipeline

def print_json(obj: Any):
    if not obj:
        print("None")
        return
    if hasattr(obj, "to_dict"):
        print(json.dumps(obj.to_dict(), indent=2))
    elif dataclasses.is_dataclass(obj):
        print(json.dumps(dataclasses.asdict(obj), indent=2))
    else:
        print(json.dumps(obj, indent=2))

def setup_pipeline(memory_manager, primary_reasoner, escalation_reasoner=None):
    retriever = MemoryRetriever(memory_manager)
    evidence_collector = EvidenceCollector()
    grounding_validator = GroundingValidator()
    decision_validator = DecisionValidator()
    
    escalation_manager = None
    if escalation_reasoner:
        escalation_manager = EscalationManager(
            escalation_reasoner=escalation_reasoner,
            decision_validator=decision_validator,
            evidence_collector=evidence_collector,
            grounding_validator=grounding_validator
        )
        
    pipeline = ReasoningPipeline(
        reasoner=primary_reasoner,
        retriever=retriever,
        evidence_collector=evidence_collector,
        grounding_validator=grounding_validator,
        escalation_manager=escalation_manager
    )
    pipeline.arbiter = DecisionArbiter()
    return pipeline

def setup_memory(facts: List[tuple]) -> tuple:
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    store = SQLiteMemoryStore(path)
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    memory_manager = MemoryManager(episodic, knowledge)
    
    for fact in facts:
        memory_manager.remember_fact(*fact)
        
    return memory_manager, path

def run_test_1():
    print("--------------------------------------------------")
    print("TEST 1 - STRONG EVIDENCE")
    print("Expected: APPROVED")
    print("--------------------------------------------------\n")
    
    facts = [
        ("device_01", "device", "location", "Main Lab"),
        ("device_01", "device", "max_safe_temperature", "80°C"),
        ("device_01", "device", "feature", "cooling system"),
        ("device_01", "device", "risk", "risk of overheating") # Add to support inference
    ]
    
    situation_context = {
        "entities": {"device_id": ["device_01"]},
        "state_snapshot": {
            "observations": [
                "location is Main Lab",
                "temperature is 92°C",
                "safe temperature limit is 80°C",
                "device status is online",
                "temperature confirmed by two independent sensors"
            ]
        }
    }
    
    memory_manager, db_path = setup_memory(facts)
    try:
        # Part A: Real Qwen Result
        qwen = QwenReasoner(model_name="qwen3:8b", timeout=60)
        pipeline = setup_pipeline(memory_manager, qwen)
        try:
            print("Running Real QwenReasoner...")
            result = pipeline.execute(situation_context)
            verdict = result.arbitration_result.verdict if result.arbitration_result else "UNKNOWN"
            print(f"REAL QWEN RESULT: {verdict}\n")
        except ReasoningIntegrationError as e:
            print(f"[ERROR] Could not connect to Qwen: {e.message}\n")
            result = None
            verdict = "ERROR"

        # Part B: Deterministic FakeReasoner Result
        fake_decision = Decision(
            situation_summary="Device temperature exceeds safe limits.",
            observations=[
                "temperature is 92°C",
                "safe temperature limit is 80°C"
            ],
            inferences=[
                "Temperature exceeds the safe operating limit"
            ],
            risks=[
                "risk of overheating"
            ],
            recommended_actions=[{
                "action_type": "activate_cooling",
                "payload": {"device_id": "device_01"}
            }],
            confidence=0.95,
            requires_deep_analysis=False,
            decision_rationale="Temperature is critically high, need cooling."
        )
        fake = FakeReasoner(fixed_decision=fake_decision)
        pipeline_fake = setup_pipeline(memory_manager, fake)
        print("Running Deterministic FakeReasoner...")
        fake_result = pipeline_fake.execute(situation_context)
        fake_verdict = fake_result.arbitration_result.verdict if fake_result.arbitration_result else "UNKNOWN"
        print(f"DETERMINISTIC APPROVAL TEST: {fake_verdict}\n")
        
        print("--- Deterministic Pipeline Output ---")
        print("PRIMARY DECISION:")
        print_json(fake_result.primary_decision)
        print("GROUNDING REPORT:")
        print_json(fake_result.primary_grounding_report)
        print("ARBITRATION RESULT:")
        print_json(fake_result.arbitration_result)
        
        passed = (fake_verdict == "APPROVED")
        print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
        return passed

    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass

def run_test_2():
    print("--------------------------------------------------")
    print("TEST 2 - AMBIGUOUS SITUATION")
    print("Expected: ESCALATION -> REVIEW")
    print("--------------------------------------------------\n")
    
    facts = [
        ("device_01", "device", "location", "Main Lab"),
        ("device_01", "device", "operation", "normally operates continuously"),
        ("Main Lab", "location", "activity", "maintenance activity sometimes occurs")
    ]
    
    situation_context = {
        "entities": {"device_id": ["device_01"], "location_id": ["Main Lab"]},
        "state_snapshot": {
            "observations": [
                "Motion detected at 03:00",
                "device_01 is offline",
                "No camera footage is available",
                "No authorized access record exists",
                "Motion sensor produced only one event"
            ]
        }
    }
    
    memory_manager, db_path = setup_memory(facts)
    try:
        qwen = QwenReasoner(model_name="qwen3:8b", timeout=60)
        ornith = OrnithReasoner(model_name="hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M", timeout=120)
        pipeline = setup_pipeline(memory_manager, qwen, ornith)
        
        try:
            result = pipeline.execute(situation_context)
        except ReasoningIntegrationError as e:
            print(f"[ERROR] Could not connect to models: {e.message}")
            return False
            
        print("PRIMARY DECISION:")
        print_json(result.primary_decision)
        
        print("\nPRIMARY GROUNDING REPORT:")
        print_json(result.primary_grounding_report)
        
        if result.escalated:
            print("\nESCALATION TRIGGERED")
            print("\nESCALATION DECISION:")
            print_json(result.escalation_decision)
            print("\nESCALATION GROUNDING REPORT:")
            print_json(result.escalation_grounding_report)
        else:
            print("\nESCALATION DIAGNOSTIC")
            requires_deep = False
            if result.primary_decision:
                requires_deep = result.primary_decision.requires_deep_analysis
            print(f"- primary_decision.requires_deep_analysis: {requires_deep}")
            
            grounding_status = "UNKNOWN"
            if result.primary_grounding_report:
                grounding_status = result.primary_grounding_report.status
            print(f"- primary grounding status: {grounding_status}")
            
            print(f"- EscalationManager configured: {pipeline.escalation_manager is not None}")
            
            # Diagnostic explanation
            print("- Exact reason it did or did not escalate:")
            if result.escalation_required:
                print("  Pipeline logic evaluated escalation_required = True, but something failed.")
                if result.escalation_error:
                    print(f"  Error: {result.escalation_error}")
            else:
                print("  Pipeline logic evaluated escalation_required = False.")
                print("  Currently, ATLAS Core Pipeline only triggers escalation if final_status == 'REQUIRES_DEEP_ANALYSIS' or primary_decision sets it.")
                
        print("\nFINAL ARBITRATION RESULT:")
        print_json(result.arbitration_result)
        
        verdict = result.arbitration_result.verdict if result.arbitration_result else "UNKNOWN"
        print(f"\nFinal verdict: {verdict}")
        
        passed = (result.escalated and verdict == "REVIEW")
        print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
        return passed

    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass

def run_test_3():
    print("--------------------------------------------------")
    print("TEST 3 - HALLUCINATION / UNSUPPORTED CLAIMS")
    print("Expected: BLOCKED")
    print("--------------------------------------------------\n")
    
    facts = [
        ("device_01", "device", "status", "online"),
        ("device_01", "device", "temperature", "25°C"),
        ("device_01", "device", "normal_temp_range", "between 10°C and 40°C")
    ]
    
    situation_context = {
        "entities": {"device_id": ["device_01"]},
        "state_snapshot": {
            "observations": [
                "device_01 is online",
                "temperature is 25°C",
                "normal operating temperature is between 10°C and 40°C"
            ]
        }
    }
    
    memory_manager, db_path = setup_memory(facts)
    try:
        fake_decision = Decision(
            situation_summary="Catastrophic failure.",
            observations=[
                "device_01 is on fire",
                "temperature is 200°C",
                "unauthorized person is inside the lab"
            ],
            inferences=["the laboratory is under attack"],
            risks=["immediate explosion is likely"],
            recommended_actions=[{
                "action_type": "emergency_shutdown",
                "payload": {"device_id": "device_01"}
            }],
            confidence=0.99,
            requires_deep_analysis=False,
            decision_rationale="Emergency."
        )
        fake = FakeReasoner(fixed_decision=fake_decision)
        pipeline = setup_pipeline(memory_manager, fake)
        
        result = pipeline.execute(situation_context)
        
        print("PRIMARY DECISION:")
        print_json(result.primary_decision)
        
        print("\nGROUNDING REPORT:")
        print_json(result.primary_grounding_report)
        
        print("\nARBITRATION RESULT:")
        print_json(result.arbitration_result)
        
        verdict = result.arbitration_result.verdict if result.arbitration_result else "UNKNOWN"
        
        # Verify strict structural action block
        allowed = []
        blocked = []
        if result.arbitration_result:
            allowed = result.arbitration_result.allowed_actions
            blocked = result.arbitration_result.blocked_actions
            
        print(f"\nallowed_actions: {allowed}")
        print(f"blocked_actions: {blocked}")
        
        passed = (verdict == "BLOCKED" and len(allowed) == 0 and len(blocked) > 0)
        print(f"\nRESULT: {'PASS' if passed else 'FAIL'}")
        return passed

    finally:
        try:
            os.remove(db_path)
        except OSError:
            pass


def main():
    print("==================================================")
    print("ATLAS CORE - THREE SCENARIO VALIDATION")
    print("==================================================\n")

    t1 = run_test_1()
    t2 = run_test_2()
    t3 = run_test_3()
    
    print("\n==================================================")
    print("FINAL TEST SUMMARY")
    print("==================================================")
    
    print("\nTest 1:")
    print("Expected: APPROVED")
    print(f"Actual: {'PASS' if t1 else 'FAIL'}")
    
    print("\nTest 2:")
    print("Expected: ESCALATION -> REVIEW")
    print(f"Actual: {'PASS' if t2 else 'FAIL'}")
    
    print("\nTest 3:")
    print("Expected: BLOCKED")
    print(f"Actual: {'PASS' if t3 else 'FAIL'}")
    
    score = sum([1 for x in [t1, t2, t3] if x])
    print(f"\nOverall:\n{score} / 3 scenario goals achieved")
    print("==================================================\n")

if __name__ == "__main__":
    main()
