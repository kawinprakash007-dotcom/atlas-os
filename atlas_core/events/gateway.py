from typing import Optional, Any, Dict
import copy
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.builder import ContextBuilder
from atlas_core.memory.manager import MemoryManager
from atlas_core.reasoning.pipeline import ReasoningPipeline, ATLASReasoningResult

class EventGateway:
    def __init__(
        self, 
        world_state: WorldState, 
        event_history: Optional[EventHistory] = None, 
        context_builder: Optional[ContextBuilder] = None,
        memory_manager: Optional[MemoryManager] = None,
        reasoning_pipeline: Optional[ReasoningPipeline] = None,
        action_executor = None,
        feedback_processor = None
    ):
        self.world_state = world_state
        self.event_history = event_history
        self.context_builder = context_builder
        self.memory_manager = memory_manager
        self.reasoning_pipeline = reasoning_pipeline
        self.action_executor = action_executor
        self.feedback_processor = feedback_processor

    def process(self, event: Event) -> Dict[str, Any]:
        if not isinstance(event, Event):
            raise ValueError("Must provide an Event instance")
        
        # 1. Validation (above)
        
        # 2. Update WorldState
        self.world_state.process_event(event)

        # 3. Add Event to EventHistory
        if self.event_history:
            self.event_history.add_event(event)

        # 4. Extract Entities & 5. Build Situation Context
        context = None
        entities = {}
        if self.context_builder:
            context = self.context_builder.build_context(event)
            entities = context.get("entities", {})
        
        # 6. Store Event in Episodic Memory
        if self.memory_manager:
            self.memory_manager.remember_event(event, entities)
            
        # 7. Execute Reasoning Pipeline
        if self.reasoning_pipeline and context is not None:
            safe_context = copy.deepcopy(context)
            reasoning_result = self.reasoning_pipeline.execute(safe_context)
            
            output = copy.deepcopy(context)
            output["reasoning_result"] = reasoning_result
            
            # 8. Action Execution
            if self.action_executor and reasoning_result.arbitration_result:
                exec_result = self.action_executor.execute(reasoning_result.arbitration_result)
                output["action_execution_result"] = exec_result
                
                # 9. Execution Feedback
                if self.feedback_processor:
                    feedback_result = self.feedback_processor.process(
                        execution_result=exec_result,
                        source_event=event
                    )
                    output["execution_feedback_result"] = feedback_result
                
            return output

        # 10. Return Result
        return context
