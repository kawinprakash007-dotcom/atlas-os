import tempfile
import os

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import FakeReasoner
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.reasoning.escalation import EscalationManager
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

def main():
    print("==================================================")
    print("ATLAS Core v0.8 — Escalation Orchestrator Demo")
    print("==================================================\n")
    
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
        memory_manager.remember_fact("device_01", "device", "status", "offline")
        
        # 3. Setup Fake Reasoners
        # Primary reasoner produces 2 unsupported inferences -> REQUIRES_DEEP_ANALYSIS
        primary_reasoner = FakeReasoner(Decision(
            situation_summary="Device is offline and motion detected.",
            observations=["device_01 is offline", "device_01 is offline"], 
            inferences=["ghosts caused the issue", "aliens stole it"], 
            risks=["unauthorized access possible"],
            recommended_actions=[{"action_type": "alert_security"}],
            confidence=0.8
        ))
        
        # Escalation reasoner produces supported inferences -> TRUSTED
        escalation_reasoner = FakeReasoner(Decision(
            situation_summary="Device is offline and motion detected. Discarded ghosts/aliens hypothesis.",
            observations=["device_01 is offline"], 
            inferences=["motion was detected"], # This will be supported by "motion detected" in context
            risks=["unauthorized access possible"],
            recommended_actions=[{"action_type": "alert_security"}],
            confidence=0.9
        ))
        
        # 4. Initialize Pipeline
        print("[2] Initializing Reasoning Pipeline and Escalation Manager...")
        retriever = MemoryRetriever(memory_manager)
        collector = EvidenceCollector()
        grounding_validator = GroundingValidator()
        decision_validator = DecisionValidator()
        
        escalation_manager = EscalationManager(
            escalation_reasoner, decision_validator, collector, grounding_validator
        )
        
        pipeline = ReasoningPipeline(
            primary_reasoner, retriever, collector, grounding_validator, escalation_manager
        )
        
        # 5. Situation Context
        situation_context = {
            "entities": {"device_id": ["device_01"]},
            "state_snapshot": {
                "sensors": {
                    "motion": "detected"
                }
            }
        }
        
        print("\n[3] Executing pipeline with situation_context...")
        result = pipeline.execute(situation_context)
        
        # 6. Print Results
        print("\n==================================================")
        print("PRIMARY DECISION")
        print(f"Inferences: {result.primary_decision.inferences}")
        print("PRIMARY GROUNDING STATUS")
        print(f"Status: {result.primary_grounding_report.status}")
        
        if result.escalated:
            print("\nESCALATION TRIGGERED")
            print("==================================================")
            print("ESCALATED DECISION")
            print(f"Inferences: {result.escalation_decision.inferences}")
            print("ESCALATED GROUNDING STATUS")
            print(f"Status: {result.escalation_grounding_report.status}")
            
        print("\n==================================================")
        print("FINAL ATLAS STATUS")
        print("==================================================")
        print(f"Final Status:            {result.final_status}")
        print(f"Escalation Required:     {result.escalation_required}")
        print(f"Action Review Required:  {result.action_review_required}")
        print(f"Blocked:                 {result.blocked}")
        print("==================================================")
        
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

if __name__ == "__main__":
    main()
