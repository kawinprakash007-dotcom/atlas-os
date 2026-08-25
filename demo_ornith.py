import tempfile
import os
import json
import traceback

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.ornith import OrnithReasoner
from atlas_core.reasoning.qwen import ReasoningIntegrationError
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

def main():
    print("==================================================")
    print("ATLAS Core v0.9 — Ornith Deep Reasoner Demo")
    print("==================================================\n")
    
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    try:
        # 1. Initialize a small temporary file-based SQLite memory database.
        store = SQLiteMemoryStore(path)
        episodic = EpisodicMemory(store)
        knowledge = KnowledgeMemory(store)
        memory_manager = MemoryManager(episodic, knowledge)
        
        # 3. Store a small amount of relevant episodic/knowledge memory.
        memory_manager.remember_fact("device_01", "device", "status", "offline")
        memory_manager.remember_fact("device_01", "device", "location", "Main Lab")
        
        # 2. Create a small situation context.
        situation_context = {
            "entities": {"device_id": ["device_01"]},
            "state_snapshot": {
                "sensors": {
                    "motion": "detected"
                }
            }
        }
        
        # 4. Create a primary decision.
        primary_decision = {
            "decision_id": "a1b2c3d4",
            "situation_summary": "Device is offline and motion detected.",
            "observations": ["device_01 is offline"], 
            "inferences": ["ghosts caused the issue", "aliens stole it"], 
            "risks": ["unauthorized access possible"],
            "recommended_actions": [{"action_type": "alert_security"}],
            "confidence": 0.8,
            "requires_deep_analysis": True
        }
        
        # 5. Create or simulate a grounding report that causes escalation.
        primary_grounding_report = {
            "status": "REQUIRES_DEEP_ANALYSIS",
            "grounding_score": 0.33,
            "supported_claims": ["device_01 is offline"],
            "unsupported_claims": ["ghosts caused the issue", "aliens stole it"],
            "uncertain_claims": []
        }
        
        # 6. Build situation_context["escalation_context"]
        situation_context["escalation_context"] = {
            "instructions": (
                "A primary reasoning system analyzed this situation but the result required deeper analysis.\n"
                "Independently re-evaluate the available information."
            ),
            "primary_decision": primary_decision,
            "primary_grounding_report": primary_grounding_report
        }
        
        # 7. Call OrnithReasoner.
        print("[*] Initializing OrnithReasoner (hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M)...")
        reasoner = OrnithReasoner(timeout=30)
        
        # Retrieve memory to simulate the pipeline passing it in
        from atlas_core.reasoning.retriever import MemoryRetriever
        retriever = MemoryRetriever(memory_manager)
        retrieved_memory = retriever.retrieve(situation_context)
        
        print("[*] Sending escalation prompt to Ollama...\n")
        try:
            decision = reasoner.reason(situation_context, retrieved_memory)
            
            # 8. Print the resulting validated Decision as formatted JSON.
            print("==================================================")
            print("ORNITH DEEP REASONER DECISION")
            print("==================================================")
            import dataclasses
            print(json.dumps(dataclasses.asdict(decision), indent=2))
            
        except ReasoningIntegrationError as e:
            # 9. Gracefully handle the case where Ollama is not running.
            print("==================================================")
            print("ESCALATION FAILED GRACEFULLY")
            print("==================================================")
            print(f"Error Phase: {e.phase}")
            print(f"Message: {e.message}")
            if e.original_error:
                print(f"Original Error: {e.original_error}")
            print("\n(This is expected if Ollama or the Ornith model is not running locally.)")
            
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

if __name__ == "__main__":
    main()
