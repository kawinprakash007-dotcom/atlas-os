import copy
from typing import Optional
import time

from atlas_core.feedback import ExecutionFeedbackResult
from atlas_core.actions.executor import ActionExecutionResult
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.memory.manager import MemoryManager

class ExecutionFeedbackProcessor:
    def __init__(
        self,
        world_state: WorldState,
        event_history: EventHistory,
        memory_manager: Optional[MemoryManager] = None
    ):
        self.world_state = world_state
        self.event_history = event_history
        self.memory_manager = memory_manager

    def process(self, execution_result: ActionExecutionResult, source_event: Optional[Event] = None) -> ExecutionFeedbackResult:
        if execution_result.skipped:
            return ExecutionFeedbackResult(
                processed_actions=0,
                successful_actions=0,
                failed_actions=0,
                world_state_updated=False,
                history_recorded=False,
                memory_stored=False,
                skipped=True,
                errors=[]
            )

        safe_execution_result = copy.deepcopy(execution_result)
        
        executed_actions = []
        for dr in safe_execution_result.executed_actions:
            executed_actions.append({
                "action_type": dr.action_type,
                "status": "SUCCESS",
                "result": dr.result
            })
            
        failed_actions = []
        for dr in safe_execution_result.failed_actions:
            failed_actions.append({
                "action_type": dr.action_type,
                "status": "FAILED",
                "error": str(dr.error) if dr.error else "Unknown error"
            })

        feedback_data = {
            "source_event_id": source_event.event_id if source_event else None,
            "verdict": safe_execution_result.verdict,
            "executed_actions": executed_actions,
            "failed_actions": failed_actions,
            "timestamp": time.time()
        }

        errors = []
        world_state_updated = False
        history_recorded = False
        memory_stored = False

        # 1. WorldState Update
        try:
            self.world_state.record_execution_batch(feedback_data)
            world_state_updated = True
        except Exception as e:
            errors.append(f"WorldState update failed: {str(e)}")

        # 2. EventHistory Feedback
        try:
            outcome_event = Event(
                source="execution_feedback",
                event_type="action_execution_result",
                priority="normal",
                payload=feedback_data
            )
            self.event_history.add_event(outcome_event)
            history_recorded = True
        except Exception as e:
            errors.append(f"EventHistory update failed: {str(e)}")

        # 3. Memory Feedback
        if self.memory_manager:
            memory_stored = True # assume true unless one fails
            for action in executed_actions:
                try:
                    outcome_event_single = Event(
                        source="execution_feedback",
                        event_type="action_execution_result",
                        priority="normal",
                        payload={"action": action, "source_event_id": feedback_data["source_event_id"]}
                    )
                    # We store it as an event in episodic memory
                    # It's an action outcome, so entities could just be empty or mapped to payload
                    self.memory_manager.remember_event(outcome_event_single, {})
                except Exception as e:
                    memory_stored = False
                    errors.append(f"MemoryManager update failed for executed action {action['action_type']}: {str(e)}")
                    
            for action in failed_actions:
                try:
                    outcome_event_single = Event(
                        source="execution_feedback",
                        event_type="action_execution_result",
                        priority="normal",
                        payload={"action": action, "source_event_id": feedback_data["source_event_id"]}
                    )
                    self.memory_manager.remember_event(outcome_event_single, {})
                except Exception as e:
                    memory_stored = False
                    errors.append(f"MemoryManager update failed for failed action {action['action_type']}: {str(e)}")

        total_processed = len(executed_actions) + len(failed_actions)

        return ExecutionFeedbackResult(
            processed_actions=total_processed,
            successful_actions=len(executed_actions),
            failed_actions=len(failed_actions),
            world_state_updated=world_state_updated,
            history_recorded=history_recorded,
            memory_stored=memory_stored,
            skipped=False,
            errors=errors
        )
