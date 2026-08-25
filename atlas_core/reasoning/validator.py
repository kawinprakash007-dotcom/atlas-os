from typing import Dict, Any
from atlas_core.reasoning.decision import Decision

class DecisionValidator:
    """
    Validates a generated Decision object for structural soundness.
    """
    def validate(self, decision: Decision) -> Dict[str, Any]:
        errors = []

        if not isinstance(decision.observations, list):
            errors.append("'observations' must be a list.")
        
        if not isinstance(decision.inferences, list):
            errors.append("'inferences' must be a list.")
            
        if not isinstance(decision.risks, list):
            errors.append("'risks' must be a list.")
            
        if not isinstance(decision.recommended_actions, list):
            errors.append("'recommended_actions' must be a list.")
        else:
            for i, action in enumerate(decision.recommended_actions):
                if not isinstance(action, dict):
                    errors.append(f"Action at index {i} must be a dictionary.")
                    continue
                if "action_type" not in action or not isinstance(action["action_type"], str) or not action["action_type"].strip():
                    errors.append(f"Action at index {i} must have a non-empty string 'action_type'.")
                if "payload" not in action or not isinstance(action["payload"], dict):
                    errors.append(f"Action at index {i} must have a dictionary 'payload'.")
            
        if not (0.0 <= decision.confidence <= 1.0):
            errors.append("'confidence' must be between 0.0 and 1.0.")

        is_valid = len(errors) == 0

        return {
            "is_valid": is_valid,
            "errors": errors
        }
