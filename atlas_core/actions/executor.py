from dataclasses import dataclass, field
from typing import List, Dict, Any

from atlas_core.reasoning.arbitration import ArbitrationResult
from atlas_core.actions.safety import ActionSafetyValidator
from atlas_core.actions.dispatcher import ActionDispatcher, ActionExecutionResult as DispatcherResult

@dataclass
class ActionExecutionResult:
    verdict: str
    executed_actions: List[DispatcherResult] = field(default_factory=list)
    blocked_actions: List[Dict[str, Any]] = field(default_factory=list)
    failed_actions: List[DispatcherResult] = field(default_factory=list)
    skipped: bool = False

class ActionExecutor:
    def __init__(
        self,
        safety_validator: ActionSafetyValidator,
        dispatcher: ActionDispatcher
    ):
        self.safety_validator = safety_validator
        self.dispatcher = dispatcher

    def execute(self, arbitration_result: ArbitrationResult) -> ActionExecutionResult:
        if arbitration_result.verdict != "APPROVED":
            return ActionExecutionResult(
                verdict=arbitration_result.verdict,
                executed_actions=[],
                blocked_actions=list(arbitration_result.allowed_actions),
                failed_actions=[],
                skipped=True
            )
            
        safety_result = self.safety_validator.validate(arbitration_result)
        
        if not safety_result.allowed_actions:
            return ActionExecutionResult(
                verdict=arbitration_result.verdict,
                executed_actions=[],
                blocked_actions=safety_result.blocked_actions,
                failed_actions=[],
                skipped=True
            )
            
        dispatch_results = self.dispatcher.dispatch(safety_result)
        
        executed = []
        failed = []
        for dr in dispatch_results:
            if dr.status == "SUCCESS":
                executed.append(dr)
            else:
                failed.append(dr)
                
        return ActionExecutionResult(
            verdict=arbitration_result.verdict,
            executed_actions=executed,
            blocked_actions=safety_result.blocked_actions,
            failed_actions=failed,
            skipped=False
        )
