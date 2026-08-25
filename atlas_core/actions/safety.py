import copy
from dataclasses import dataclass
from typing import List, Dict, Any
from atlas_core.reasoning.arbitration import ArbitrationResult
from atlas_core.actions.registry import ActionRegistry

@dataclass
class ActionSafetyResult:
    safe: bool
    allowed_actions: List[Dict[str, Any]]
    blocked_actions: List[Dict[str, Any]]
    reasons: List[str]

class ActionSafetyValidator:
    def __init__(self, registry: ActionRegistry):
        self.registry = registry

    def validate(self, arbitration_result: ArbitrationResult) -> ActionSafetyResult:
        if arbitration_result.verdict != "APPROVED":
            return ActionSafetyResult(
                safe=False,
                allowed_actions=[],
                blocked_actions=copy.deepcopy(arbitration_result.allowed_actions),
                reasons=[f"Arbitration verdict is {arbitration_result.verdict}, only APPROVED actions can execute."]
            )

        allowed = []
        blocked = []
        reasons = []

        for action in arbitration_result.allowed_actions:
            if not isinstance(action, dict):
                blocked.append(copy.deepcopy(action))
                reasons.append("Action is not a dictionary.")
                continue

            action_type = action.get("action_type")
            if not action_type:
                blocked.append(copy.deepcopy(action))
                reasons.append("Action missing 'action_type'.")
                continue

            payload = action.get("payload")
            if payload is None:
                blocked.append(copy.deepcopy(action))
                reasons.append(f"Action '{action_type}' missing 'payload'.")
                continue

            if not isinstance(payload, dict):
                blocked.append(copy.deepcopy(action))
                reasons.append(f"Action '{action_type}' payload must be a dictionary.")
                continue

            definition = self.registry.get_action(action_type)
            if not definition:
                blocked.append(copy.deepcopy(action))
                reasons.append(f"Unknown action type: {action_type}")
                continue

            missing_fields = [field for field in definition.required_fields if field not in payload]
            if missing_fields:
                blocked.append(copy.deepcopy(action))
                reasons.append(f"Action '{action_type}' missing required payload fields: {missing_fields}")
                continue

            allowed.append(copy.deepcopy(action))

        is_safe = len(allowed) > 0 and len(blocked) == 0

        return ActionSafetyResult(
            safe=is_safe,
            allowed_actions=allowed,
            blocked_actions=blocked,
            reasons=reasons
        )
