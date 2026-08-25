import json
from typing import Dict, Any
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.events.event import Event
from atlas_core.context.builder import ContextBuilder
from atlas_core.context.entities import EntityExtractor
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.escalation import EscalationManager

from atlas_core.actions.registry import ActionRegistry
from atlas_core.actions.safety import ActionSafetyValidator
from atlas_core.actions.dispatcher import ActionDispatcher
from atlas_core.actions.executor import ActionExecutor

from atlas_core.events.gateway import EventGateway

def print_json(data):
    print(json.dumps(data, indent=2, default=str))

class FakeReasoner:
    def __init__(self, fixed_decision: Decision):
        self.fixed_decision = fixed_decision
    def reason(self, situation: Dict[str, Any], memory: Dict[str, Any]) -> Decision:
        return self.fixed_decision

def activate_cooling(payload):
    return {
        "status": "cooling_activated",
        "device_id": payload.get("device_id")
    }

def investigate(payload):
    return {
        "status": "investigation_started"
    }

def main():
    print("==================================================")
    print("ATLAS CORE - END-TO-END EXECUTION DEMO")
    print("==================================================\n")

    # Set up Action Execution
    registry = ActionRegistry()
    registry.register("activate_cooling", ["device_id"], activate_cooling)
    registry.register("investigate", ["location"], investigate)

    validator = ActionSafetyValidator(registry)
    dispatcher = ActionDispatcher(registry)
    executor = ActionExecutor(validator, dispatcher)

    import tempfile
    import os
    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    # Set up Memory
    store = SQLiteMemoryStore(path)
    memory_manager = MemoryManager(EpisodicMemory(store), KnowledgeMemory(store))

    # Set up Gateway Core
    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)

    # Scenarios
    scenarios = [
        {
            "name": "SCENARIO 1 - APPROVED",
            "event": Event("sensor_x", "sensor_alert", "normal", {"temperature": 92, "device_id": "sensor_x"}),
            "facts": [
                ("sensor_x", "device", "temperature", "92"),
                ("sensor_x", "device", "safe limit", "80"),
                ("sensor_x", "device", "status", "overheating")
            ],
            "decision": Decision(
                situation_summary="Temperature exceeds safe limits.",
                decision_rationale="Overheating evident.",
                observations=["sensor_x device temperature 92", "sensor_x device safe limit 80"],
                inferences=["sensor_x device status overheating"],
                risks=[],
                recommended_actions=[{"action_type": "activate_cooling", "payload": {"device_id": "sensor_x"}}],
                confidence=0.9
            ),
            "expected_verdict": "APPROVED",
            "expected_action_state": "EXECUTED"
        },
        {
            "name": "SCENARIO 2 - AMBIGUOUS",
            "event": Event("sensor_x", "sensor_alert", "normal", {"motion": True, "time": "03:00", "device_id": "sensor_x"}),
            "facts": [],
            "decision": Decision(
                situation_summary="Motion detected, device offline.",
                decision_rationale="Ambiguous.",
                observations=["Motion detected at 03:00", "sensor_x is offline", "No camera footage"],
                inferences=["Possible intrusion"],
                risks=["Theft"],
                recommended_actions=[{"action_type": "investigate", "payload": {"location": "lab_1"}}],
                confidence=0.85,
                requires_deep_analysis=True
            ),
            "expected_verdict": "REVIEW",
            "expected_action_state": "SKIPPED"
        },
        {
            "name": "SCENARIO 3 - HALLUCINATION",
            "event": Event("sensor_x", "sensor_alert", "normal", {"temperature": 25, "device_id": "sensor_x"}),
            "facts": [],
            "decision": Decision(
                situation_summary="Catastrophic failure.",
                decision_rationale="Emergency.",
                observations=["sensor_x is on fire", "temperature is 200"],
                inferences=["laboratory under attack"],
                risks=["explosion"],
                recommended_actions=[{"action_type": "emergency_shutdown", "payload": {}}],
                confidence=0.99
            ),
            "expected_verdict": "BLOCKED",
            "expected_action_state": "SKIPPED"
        }
    ]

    for sc in scenarios:
        print(f"==================================================")
        print(sc["name"])
        print(f"Expected: {sc['expected_verdict']} -> {sc['expected_action_state']}")
        print(f"==================================================\n")

        # Load facts
        for f in sc["facts"]:
            memory_manager.remember_fact(f[0], f[1], f[2], f[3])

        # Pipeline setup
        reasoner = FakeReasoner(sc["decision"])
        retriever = MemoryRetriever(memory_manager)
        collector = EvidenceCollector()
        decision_validator = DecisionValidator()
        grounding_validator = GroundingValidator()
        escalation_manager = EscalationManager(FakeReasoner(sc["decision"]), decision_validator, collector, grounding_validator)
        pipeline = ReasoningPipeline(reasoner, retriever, collector, grounding_validator, escalation_manager)

        gateway = EventGateway(
            world_state=world,
            event_history=history,
            context_builder=builder,
            memory_manager=memory_manager,
            reasoning_pipeline=pipeline,
            action_executor=executor
        )

        result = gateway.process(sc["event"])
        reasoning = result["reasoning_result"]
        action_res = result["action_execution_result"]

        print("Grounding Status:", reasoning.primary_grounding_report.status)
        if reasoning.primary_grounding_report.status == "REJECTED":
            print("Unsupported Claims:")
            for uc in reasoning.primary_grounding_report.unsupported_claims:
                print(f"  - {uc}")

        print("Arbitration Verdict:", reasoning.arbitration_result.verdict)
        
        if reasoning.arbitration_result.verdict == "APPROVED":
            print("Allowed Actions:")
            print_json(reasoning.arbitration_result.allowed_actions)
        else:
            print("Blocked Actions:")
            print_json(reasoning.arbitration_result.blocked_actions)

        print("\nAction Execution Result:")
        print_json({
            "verdict": action_res.verdict,
            "skipped": action_res.skipped,
            "executed": [r.action_type for r in action_res.executed_actions],
            "failed": [r.action_type for r in action_res.failed_actions],
            "blocked": [a.get("action_type", "unknown") for a in action_res.blocked_actions]
        })

        if action_res.skipped and sc["expected_action_state"] == "SKIPPED":
            print("\nRESULT: PASS")
        elif not action_res.skipped and sc["expected_action_state"] == "EXECUTED":
            print("\nRESULT: PASS")
        else:
            print("\nRESULT: FAIL")
        print("\n")

if __name__ == "__main__":
    main()
