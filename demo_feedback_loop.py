import json
import tempfile
import os
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

from atlas_core.feedback.processor import ExecutionFeedbackProcessor
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

def emergency_shutdown(payload):
    return {
        "status": "shutdown_complete"
    }

def main():
    print("==================================================")
    print("ATLAS CORE - FEEDBACK LOOP DEMO")
    print("==================================================\n")

    # Set up Action Execution
    registry = ActionRegistry()
    registry.register("activate_cooling", ["device_id"], activate_cooling)
    registry.register("investigate", ["location"], investigate)
    registry.register("emergency_shutdown", [], emergency_shutdown)

    validator = ActionSafetyValidator(registry)
    dispatcher = ActionDispatcher(registry)
    executor = ActionExecutor(validator, dispatcher)

    fd, path = tempfile.mkstemp()
    os.close(fd)
    
    store = SQLiteMemoryStore(path)
    memory_manager = MemoryManager(EpisodicMemory(store), KnowledgeMemory(store))

    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)

    feedback_processor = ExecutionFeedbackProcessor(world, history, memory_manager)

    scenarios = [
        {
            "name": "SCENARIO 1 - SUCCESSFUL ACTION FEEDBACK",
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
            "expected_skipped": False
        },
        {
            "name": "SCENARIO 2 - REVIEW",
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
            "expected_skipped": True
        },
        {
            "name": "SCENARIO 3 - BLOCKED",
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
            "expected_skipped": True
        }
    ]

    for sc in scenarios:
        print(f"==================================================")
        print(sc["name"])
        print(f"Expected: {sc['expected_verdict']} -> SKIPPED: {sc['expected_skipped']}")
        print(f"==================================================\n")

        for f in sc["facts"]:
            memory_manager.remember_fact(f[0], f[1], f[2], f[3])

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
            action_executor=executor,
            feedback_processor=feedback_processor
        )

        result = gateway.process(sc["event"])
        reasoning = result["reasoning_result"]
        action_res = result["action_execution_result"]
        feedback_res = result["execution_feedback_result"]

        if sc["name"] == "SCENARIO 1 - SUCCESSFUL ACTION FEEDBACK":
            print("Grounding Status:", reasoning.primary_grounding_report.status)
            print("Arbitration Verdict:", reasoning.arbitration_result.verdict)
            print("\nAction Execution Result:")
            print_json({
                "verdict": action_res.verdict,
                "executed": [r.action_type for r in action_res.executed_actions],
                "failed": [r.action_type for r in action_res.failed_actions],
                "skipped": action_res.skipped
            })
            print("\nExecution Feedback Result:")
            print_json({
                "processed_actions": feedback_res.processed_actions,
                "successful_actions": feedback_res.successful_actions,
                "world_state_updated": feedback_res.world_state_updated,
                "history_recorded": feedback_res.history_recorded,
                "memory_stored": feedback_res.memory_stored
            })
            print("\nRelevant WorldState:")
            print_json(world.last_execution_batch)
            print("\nRecent execution history:")
            recent = history.get_recent(5)
            for e in recent:
                if e.event_type == "action_execution_result":
                    print_json(e.payload)
        else:
            if sc["name"] == "SCENARIO 3 - BLOCKED":
                print("Blocked Actions:")
                print_json(reasoning.arbitration_result.blocked_actions)
            print("\nActions Executed:", feedback_res.processed_actions)
            print("Feedback Result:")
            print_json({
                "skipped": feedback_res.skipped,
                "processed_actions": feedback_res.processed_actions
            })

        print("\n")

if __name__ == "__main__":
    main()
