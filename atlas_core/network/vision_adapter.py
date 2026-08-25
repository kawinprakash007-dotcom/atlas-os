import copy
from typing import Dict, Any, Tuple
from atlas_core.network.schemas import VisionEvent

class VisionEventAdapter:
    """
    Translates validated external ATLAS Vision messages to internal ATLAS formats.
    Acts as a pure, read-only translation boundary without reasoning or execution capability.
    """
    @staticmethod
    def normalize(event: VisionEvent) -> Tuple[str, Dict[str, Any]]:
        # Deep-copy mutable input before transformation
        event_dict = copy.deepcopy(event.model_dump())
        event_type = event_dict.pop("event_type")

        # If incoming event has a nested payload field, use it.
        # Otherwise, treat the remaining top-level fields as the payload (flat structure).
        if "payload" in event_dict and isinstance(event_dict["payload"], dict):
            payload = event_dict.pop("payload")
            # Store remaining fields as metadata inside payload
            if event_dict:
                payload["_vision_metadata"] = event_dict
        else:
            payload = event_dict

        # Compatibility mapping:
        # Map anonymous_person_id to person_id to allow existing WorldState logic to recognize it.
        if "anonymous_person_id" in payload and "person_id" not in payload:
            payload["person_id"] = payload["anonymous_person_id"]

        return event_type, payload
