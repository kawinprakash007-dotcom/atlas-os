import sys
import os
import tempfile
import json
import dataclasses
from typing import Any

from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.memory.manager import MemoryManager

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
    if hasattr(obj, "to_dict"):
        print(json.dumps(obj.to_dict(), indent=2))
    elif dataclasses.is_dataclass(obj):
        print(json.dumps(dataclasses.asdict(obj), indent=2))
    else:
        print(json.dumps(obj, indent=2))

def main():
    print("==================================================")
    print("ATLAS CORE — FULL REASONING PIPELINE TEST")
    print("==================================================\n")

    print("[1/6] Initializing memory...")
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    try:
        # DB Setup
        store = SQLiteMemoryStore(path)
        episodic = EpisodicMemory(store)
        knowledge = KnowledgeMemory(store)
        memory_manager = MemoryManager(episodic, knowledge)
        
        # Store Knowledge
        memory_manager.remember_fact("device_01", "device", "location", "Main Lab")
        memory_manager.remember_fact("device_01", "device", "status", "offline")
        
        print("\n[2/6] Building situation context...")
        situation_context = {
            "entities": {
                "device_id": ["device_01"]
            },
            "state_snapshot": {
                "observations": [
                    "Motion detected in Main Lab",
                    "Event occurred at approximately 03:00",
                    "The motion source is unknown",
                    "No confirmation exists that the motion was unauthorized",
                    "No direct evidence confirms a security breach"
                ]
            }
        }
        
        print("\n[3/6] Running Qwen primary reasoning...")
        # Pipeline components
        retriever = MemoryRetriever(memory_manager)
        primary_reasoner = QwenReasoner(model_name="qwen3:8b", timeout=60)
        escalation_reasoner = OrnithReasoner(model_name="hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M", timeout=120)
        
        evidence_collector = EvidenceCollector()
        grounding_validator = GroundingValidator()
        decision_validator = DecisionValidator()
        
        escalation_manager = EscalationManager(
            escalation_reasoner=escalation_reasoner,
            decision_validator=decision_validator,
            evidence_collector=evidence_collector,
            grounding_validator=grounding_validator
        )
        
        # Notice we inject the escalation_manager for Deep Analysis
        pipeline = ReasoningPipeline(
            reasoner=primary_reasoner,
            retriever=retriever,
            evidence_collector=evidence_collector,
            grounding_validator=grounding_validator,
            escalation_manager=escalation_manager
        )
        
        # We override the pipeline's arbiter to ensure we run real arbitration 
        # (Though ReasoningPipeline __init__ injects it by default anyway in v1.0)
        pipeline.arbiter = DecisionArbiter()
        
        try:
            result = pipeline.execute(situation_context)
        except ReasoningIntegrationError as e:
            print(f"\n[ERROR] Could not connect to or parse model: {e.phase}")
            print(e.message)
            print("Make sure Ollama is running and the required models (qwen3:8b, ornith-1.5-9b) are available.")
            sys.exit(1)
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {str(e)}")
            sys.exit(1)

        print("\n================ PRIMARY DECISION ================\n")
        print_json(result.primary_decision)
        
        print("\n[4/6] Validating evidence grounding...")
        print("\n================ GROUNDING REPORT ================\n")
        print_json(result.primary_grounding_report)
        
        print("\n[5/6] Checking escalation...")
        if result.escalated:
            print("\nESCALATION TRIGGERED\n")
            if result.escalation_error:
                print(f"[ERROR] Escalation failed: {result.escalation_error}")
            elif result.escalation_decision:
                print("\n================ ORNITH ESCALATION DECISION ================\n")
                print_json(result.escalation_decision)
                print("\n================ ESCALATION GROUNDING REPORT ================\n")
                print_json(result.escalation_grounding_report)
        else:
            print("\nNO ESCALATION REQUIRED\n")
            
        print("\n[6/6] Final arbitration...")
        print("\n================ ARBITRATION RESULT ================\n")
        if result.arbitration_result:
            print_json(result.arbitration_result)
        else:
            print("No arbitration result found.")
            
        print("\n==================================================")
        verdict = result.arbitration_result.verdict if result.arbitration_result else "UNKNOWN"
        print(f"FINAL ATLAS VERDICT: {verdict}")
        print("==================================================")

    finally:
        try:
            os.remove(path)
        except OSError:
            pass

if __name__ == "__main__":
    main()
