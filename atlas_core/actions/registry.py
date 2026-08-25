from dataclasses import dataclass
from typing import List, Callable, Optional, Dict, Any

@dataclass
class ActionDefinition:
    action_type: str
    required_fields: List[str]
    handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

class ActionRegistry:
    def __init__(self):
        self._actions: Dict[str, ActionDefinition] = {}

    def register(self, action_type: str, required_fields: List[str], handler: Optional[Callable] = None):
        if action_type in self._actions:
            raise ValueError(f"Action '{action_type}' is already registered.")
        
        self._actions[action_type] = ActionDefinition(
            action_type=action_type,
            required_fields=required_fields,
            handler=handler
        )

    def get_action(self, action_type: str) -> Optional[ActionDefinition]:
        return self._actions.get(action_type)

    def is_registered(self, action_type: str) -> bool:
        return action_type in self._actions
