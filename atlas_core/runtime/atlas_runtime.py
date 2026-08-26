import os
import copy
import tempfile
from typing import Dict, Any, Optional, Callable

from atlas_core.runtime.configuration import ATLASConfiguration
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager
from atlas_core.commands.registry import CommandRegistry
from atlas_core.commands.dispatcher import DeviceCommandDispatcher
from atlas_core.commands.manager import DeviceCommandManager

# World
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.events.event import Event

# Context
from atlas_core.context.builder import ContextBuilder
from atlas_core.context.entities import EntityExtractor

# Memory
from atlas_core.memory.manager import MemoryManager
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

# Reasoning
from atlas_core.reasoning.pipeline import ReasoningPipeline
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.reasoning.evidence import EvidenceCollector
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.grounding import GroundingValidator
from atlas_core.reasoning.escalation import EscalationManager

# Actions
from atlas_core.actions.registry import ActionRegistry
from atlas_core.actions.safety import ActionSafetyValidator
from atlas_core.actions.dispatcher import ActionDispatcher
from atlas_core.actions.executor import ActionExecutor

# Feedback
from atlas_core.feedback.processor import ExecutionFeedbackProcessor

# Gateway
from atlas_core.events.gateway import EventGateway


class ATLASRuntime:
    def __init__(
        self,
        primary_reasoner,
        escalation_reasoner=None,
        configuration: Optional[ATLASConfiguration] = None,
        world_state: Optional[WorldState] = None,
        event_history: Optional[EventHistory] = None,
        memory_store: Optional[SQLiteMemoryStore] = None,
        device_registry: Optional[DeviceRegistry] = None,
        device_health_manager: Optional[DeviceHealthManager] = None,
        command_registry: Optional[CommandRegistry] = None,
        command_dispatcher: Optional[DeviceCommandDispatcher] = None,
        command_manager: Optional[DeviceCommandManager] = None
    ):
        if primary_reasoner is None:
            raise ValueError("ATLASRuntime requires a primary_reasoner. No safe default reasoner exists.")

        self.configuration = configuration or ATLASConfiguration()
        
        # Device Layer (Single Source of Truth)
        self.device_registry = device_registry or DeviceRegistry()
        self.device_health_manager = device_health_manager or DeviceHealthManager(
            self.device_registry,
            stale_threshold=self.configuration.device_stale_threshold,
            offline_threshold=self.configuration.device_offline_threshold
        )
        
        # Command & Control Layer
        self.command_registry = command_registry or CommandRegistry()
        self.command_dispatcher = command_dispatcher or DeviceCommandDispatcher()
        self.command_manager = command_manager or DeviceCommandManager(
            device_registry=self.device_registry,
            command_registry=self.command_registry,
            command_dispatcher=self.command_dispatcher,
            health_manager=self.device_health_manager
        )
        
        # Core World State
        self.world_state = world_state or WorldState()
        self.event_history = event_history or EventHistory()
        
        # Memory Infrastructure
        if memory_store is None:
            db_path = self.configuration.db_path
            if not db_path or db_path == ":memory:":
                # SQLite ':memory:' is isolated per connection in python's sqlite3 by default.
                # To guarantee safe operation across all modules, we use a temp file.
                fd, path = tempfile.mkstemp(prefix="atlas_mem_", suffix=".db")
                os.close(fd)
                db_path = path
            self.memory_store = SQLiteMemoryStore(db_path)
        else:
            self.memory_store = memory_store

        self.memory_manager = MemoryManager(
            EpisodicMemory(self.memory_store),
            KnowledgeMemory(self.memory_store)
        )

        # Context Building
        self.entity_extractor = EntityExtractor()
        self.context_builder = ContextBuilder(
            world_state=self.world_state,
            event_history=self.event_history,
            entity_extractor=self.entity_extractor
        )

        # Reasoning Dependencies
        self.memory_retriever = MemoryRetriever(self.memory_manager)
        self.evidence_collector = EvidenceCollector()
        self.decision_validator = DecisionValidator()
        self.grounding_validator = GroundingValidator()

        # Escalation
        self.escalation_manager = None
        if self.configuration.enable_escalation and escalation_reasoner:
            self.escalation_manager = EscalationManager(
                deep_reasoner=escalation_reasoner,
                decision_validator=self.decision_validator,
                evidence_collector=self.evidence_collector,
                grounding_validator=self.grounding_validator
            )

        self.reasoning_pipeline = ReasoningPipeline(
            reasoner=primary_reasoner,
            retriever=self.memory_retriever,
            evidence_collector=self.evidence_collector,
            grounding_validator=self.grounding_validator,
            escalation_manager=self.escalation_manager
        )

        # Action Execution
        self.action_registry = ActionRegistry()
        self.action_safety_validator = ActionSafetyValidator(self.action_registry)
        self.action_dispatcher = ActionDispatcher(self.action_registry)
        self.action_executor = ActionExecutor(
            safety_validator=self.action_safety_validator,
            dispatcher=self.action_dispatcher
        )

        # Feedback
        self.feedback_processor = ExecutionFeedbackProcessor(
            world_state=self.world_state,
            event_history=self.event_history,
            memory_manager=self.memory_manager
        )

        # Unified Gateway
        self.event_gateway = EventGateway(
            world_state=self.world_state,
            event_history=self.event_history,
            context_builder=self.context_builder,
            memory_manager=self.memory_manager,
            reasoning_pipeline=self.reasoning_pipeline,
            action_executor=self.action_executor,
            feedback_processor=self.feedback_processor
        )

    def register_action(self, action_type: str, handler: Callable, required_fields: Optional[list] = None):
        """Delegates strictly to ActionRegistry. Bypasses nothing."""
        self.action_registry.register(action_type, required_fields or [], handler)

    def process_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main unified entry point.
        Preserves caller payload immutability.
        Builds the Event and triggers the EventGateway pipeline.
        """
        # 1. Preserve payload immutability
        safe_payload = copy.deepcopy(payload)
        
        # 2. Build Event 
        # Attempt to extract a reliable source ID from the payload if standard keys exist,
        # otherwise default to "system"
        source = safe_payload.get("device_id") or safe_payload.get("person_id") or "system"
        
        event = Event(
            source=str(source),
            event_type=event_type,
            priority="normal",
            payload=safe_payload
        )

        # 3. Gateway Process (Full end-to-end traversal)
        return self.event_gateway.process(event)
