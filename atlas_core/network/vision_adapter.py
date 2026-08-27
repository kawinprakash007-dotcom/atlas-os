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
        event_type = event_dict.pop("event_type", "UNKNOWN")
        source = event_dict.get("source", "UNKNOWN")

        # If incoming event has a nested payload field, use it.
        # Otherwise, treat the remaining top-level fields as the payload (flat structure).
        if "payload" in event_dict and isinstance(event_dict["payload"], dict):
            payload = event_dict.pop("payload")
            # Store remaining fields as metadata inside payload
            if event_dict:
                payload["_vision_metadata"] = event_dict
        else:
            payload = event_dict

        # Ensure payload is a dictionary
        if not isinstance(payload, dict):
            payload = {}

        # Initialize metadata dict if missing
        if "_vision_metadata" not in payload:
            payload["_vision_metadata"] = {}

        # Add source-aware identifiers for remote systems
        is_remote = (
            source == "REMOTE_VISION" or 
            (isinstance(source, str) and (source.startswith("REMOTE_") or source.startswith("remote_")))
        )
        payload["_vision_metadata"]["is_remote"] = is_remote
        payload["_vision_metadata"]["original_source"] = source

        # Compatibility mapping and ID safety enforcement:
        anon_id = payload.get("anonymous_person_id")
        person_id = payload.get("person_id")
        
        if anon_id and str(anon_id).upper().startswith("TRACK-"):
            payload["track_id"] = anon_id
            if "person_id" not in payload:
                payload["person_id"] = None
        elif anon_id and not person_id:
            payload["person_id"] = anon_id

        # Downgrade TRACK-* IDs — they must never become authoritative person_ids.
        # Check both "person_id" and any other claim fields
        for pid_field in ["person_id", "person_id_claimed"]:
            current_pid = payload.get(pid_field)
            if current_pid and str(current_pid).upper().startswith("TRACK-"):
                payload["track_id"] = current_pid
                payload[pid_field] = None

        return event_type, payload
