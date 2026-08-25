import copy
from dataclasses import dataclass
from typing import Dict, Any, List
from atlas_core.actions.registry import ActionRegistry
from atlas_core.actions.safety import ActionSafetyResult

@dataclass
class ActionExecutionResult:
    action_type: str
    status: str
    result: Any = None
    error: str = None

class ActionDispatcher:
    def __init__(self, registry: ActionRegistry):
        self.registry = registry

    def dispatch(self, safety_result: ActionSafetyResult) -> List[ActionExecutionResult]:
        execution_results = []
        
        for action in safety_result.allowed_actions:
            action_type = action.get("action_type")
            payload = copy.deepcopy(action.get("payload", {}))
            
            definition = self.registry.get_action(action_type)
            
            if not definition:
                execution_results.append(ActionExecutionResult(
                    action_type=action_type,
                    status="FAILED",
                    error="Action definition not found in registry at dispatch time."
                ))
                continue
                
            if not definition.handler:
                execution_results.append(ActionExecutionResult(
                    action_type=action_type,
                    status="SKIPPED",
                    error="No handler associated with this action."
                ))
                continue
                
            try:
                result = definition.handler(payload)
                execution_results.append(ActionExecutionResult(
                    action_type=action_type,
                    status="SUCCESS",
                    result=result
                ))
            except Exception as e:
                execution_results.append(ActionExecutionResult(
                    action_type=action_type,
                    status="FAILED",
                    error=str(e)
                ))
                
        return execution_results
