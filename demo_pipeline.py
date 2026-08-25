import json
from pprint import pprint

from atlas_core.events.gateway import EventGateway
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

def main():
    print("==================================================")
    print("ATLAS Core v0.7 — Decision Pipeline Orchestrator Demo")
    print("==================================================\n")
    
    import tempfile
    import os
    
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    try:
        # 1. Initialize DB
        store = SQLiteMemoryStore(path)
        episodic = EpisodicMemory(store)
        knowledge = KnowledgeMemory(store)
        memory_manager = MemoryManager(episodic, knowledge)
    
    # 2. Add some facts to memory
    print("[1] Storing initial facts in memory...")
    memory_manager.remember_fact("device_01", "device", "location", "Main Lab")
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    # 3. Setup Fake Reasoner with a hardcoded decision
    fake_decision = Decision(
        situation_summary="Device is offline and motion detected.",
        observations=["device_01 is offline", "motion was detected"],
        inferences=["someone may be in the main lab", "device_01 is online"], # One uncertain, one contradicted!
        risks=["unauthorized access possible"],
        recommended_actions=[{"action_type": "alert_security"}],
        confidence=0.8
    )
    reasoner = FakeReasoner(fake_decision)
    
    # 4. Initialize Pipeline
    print("[2] Initializing Reasoning Pipeline...")
    retriever = MemoryRetriever(memory_manager)
    collector = EvidenceCollector()
    validator = GroundingValidator()
    
    pipeline = ReasoningPipeline(reasoner, retriever, collector, validator)
    
    # 5. Situation Context
    situation_context = {
        "event": "sensor_update",
        "data": {
            "sensor_id": "sensor_x",
            "motion": "detected"
        }
    }
    
    print("\n[3] Executing pipeline with situation_context:")
    pprint(situation_context)
    print("\n--- Pipeline Running ---\n")
    
    # 6. Execute Pipeline
    result = pipeline.execute(situation_context)
    
    # 7. Print Result
    print("==================================================")
    print("FINAL ATLAS REASONING RESULT")
    print("==================================================")
    print(f"Final Status:            {result.final_status}")
    print(f"Escalation Required:     {result.escalation_required}")
    print(f"Action Review Required:  {result.action_review_required}")
    print(f"Blocked:                 {result.blocked}")
    print("--------------------------------------------------")
    print("Grounding Score:         {:.2f}".format(result.grounding_report.grounding_score))
    print("\nSupported Claims:")
    for c in result.grounding_report.supported_claims:
        print(f"  [+] {c}")
    print("\nUncertain Claims:")
    for c in result.grounding_report.uncertain_claims:
        print(f"  [?] {c}")
    print("\nUnsupported Claims:")
    for c in result.grounding_report.unsupported_claims:
        print(f"  [-] {c}")
    print("==================================================")
    
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

if __name__ == "__main__":
    main()
