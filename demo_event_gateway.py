import os
import json
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder
from atlas_core.events.gateway import EventGateway
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.reasoning.decision import Decision
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.engine import BaseReasoner

class FakeReasoner(BaseReasoner):
    def __init__(self, fixed_decision=None):
        self.fixed_decision = fixed_decision

    def reason(self, situation_context, retrieved_memory):
        return self.fixed_decision

def print_json(obj):
    if not obj:
        print("None")
        return
    if hasattr(obj, "to_dict"):
        print(json.dumps(obj.to_dict(), indent=2))
    elif hasattr(obj, "__dict__"):
        print(json.dumps(obj.__dict__, indent=2))
    else:
        print(obj)

import tempfile
import atexit

def setup_pipeline_with_fake(decision, facts):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    # Cleanup temp file on exit
    def cleanup():
        try:
            os.remove(path)
        except OSError:
            pass
    atexit.register(cleanup)
    
    store = SQLiteMemoryStore(path)
    manager = MemoryManager(
        EpisodicMemory(store), 
        KnowledgeMemory(store)
    )
    for f in facts:
        manager.remember_fact(f[0], f[1], f[2], f[3])
        
    retriever = MemoryRetriever(manager)
    collector = EvidenceCollector()
    validator = GroundingValidator()
    
    reasoner = FakeReasoner(fixed_decision=decision)
    
    pipeline = ReasoningPipeline(
        reasoner=reasoner,
        retriever=retriever,
        evidence_collector=collector,
        grounding_validator=validator
    )
    return pipeline

def create_gateway(pipeline=None):
    world_state = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    context_builder = ContextBuilder(world_state, history, extractor)
    return EventGateway(
        world_state=world_state,
        event_history=history,
        context_builder=context_builder,
        reasoning_pipeline=pipeline
    )

def run_scenario(name, event_data, facts, decision, expected_verdict):
    print("\n==================================================")
    print(f"SCENARIO: {name}")
    print(f"Expected Verdict: {expected_verdict}")
    print("==================================================")
    
    pipeline = setup_pipeline_with_fake(decision, facts)
    gateway = create_gateway(pipeline)
    
    event = Event(
        source="sensor_x",
        event_type="sensor_alert",
        priority="normal",
        payload=event_data
    )
    
    print("\nEVENT RECEIVED")
    print("->")
    
    result = gateway.process(event)
    
    print("\nSITUATION CONTEXT")
    print_json(result.get("context"))
    print("->")
    
    reasoning = result.get("reasoning_result")
    
    print("\nPRIMARY REASONING")
    print_json(reasoning.primary_decision)
    print("->")
    
    print("\nGROUNDING")
    print_json(reasoning.primary_grounding_report)
    print("->")
    
    print("\nESCALATION STATUS")
    print(f"Escalation Required: {reasoning.escalation_required}")
    print("->")
    
    print("\nARBITRATION")
    print_json(reasoning.arbitration_result)
    
    verdict = reasoning.arbitration_result.verdict if reasoning.arbitration_result else "UNKNOWN"
    print(f"\nFINAL VERDICT: {verdict}")
    print(f"RESULT: {'PASS' if verdict == expected_verdict else 'FAIL'}")
    return verdict == expected_verdict


def main():
    print("==================================================")
    print("ATLAS CORE - EVENT GATEWAY INTEGRATION TEST")
    print("==================================================")

    # Scenario A: Strong Evidence -> APPROVED
    decision_a = Decision(
        situation_summary="Temperature exceeds safe limits.",
        observations=["sensor_x temperature is 92", "safe limit is 80"],
        inferences=["sensor_x is overheating"],
        risks=["damage"],
        recommended_actions=[{"action_type": "cool_down"}],
        confidence=0.9,
        requires_deep_analysis=False,
        decision_rationale="Overheating evident."
    )
    facts_a = [
        ("sensor_x", "device", "temperature", "92"),
        ("sensor_x", "device", "safe limit", "80")
    ]
    data_a = {"temperature": 92, "safe_limit": 80, "entities": {"device_id": ["sensor_x"]}}
    
    run_scenario("A: Strong Evidence", data_a, facts_a, decision_a, "APPROVED")
    
    # Scenario B: Ambiguous -> REVIEW
    decision_b = Decision(
        situation_summary="Motion detected, device offline.",
        observations=["Motion detected at 03:00", "sensor_x is offline", "No camera footage"],
        inferences=["Possible intrusion"],
        risks=["Theft"],
        recommended_actions=[],
        confidence=0.85,
        requires_deep_analysis=True,
        decision_rationale="Ambiguous."
    )
    facts_b = [
        ("sensor_x", "device", "location", "Main Lab"),
        ("Main Lab", "location", "activity", "maintenance")
    ]
    data_b = {"motion": True, "time": "03:00", "entities": {"device_id": ["sensor_x"]}}
    
    run_scenario("B: Ambiguous Event", data_b, facts_b, decision_b, "REVIEW")
    
    # Scenario C: Hallucination -> BLOCKED
    decision_c = Decision(
        situation_summary="Catastrophic failure.",
        observations=["sensor_x is on fire", "temperature is 200", "unauthorized person inside"],
        inferences=["laboratory under attack"],
        risks=["explosion"],
        recommended_actions=[{"action_type": "emergency_shutdown"}],
        confidence=0.99,
        requires_deep_analysis=False,
        decision_rationale="Emergency."
    )
    facts_c = [
        ("sensor_x", "device", "status", "online"),
        ("sensor_x", "device", "temperature", "25")
    ]
    data_c = {"temperature": 25, "entities": {"device_id": ["sensor_x"]}}
    
    run_scenario("C: Hallucination / Unsupported Claims", data_c, facts_c, decision_c, "BLOCKED")

if __name__ == "__main__":
    main()
