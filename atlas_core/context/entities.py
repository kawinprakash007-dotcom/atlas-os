from typing import Dict, Any, List

class EntityExtractor:
    KNOWN_KEYS = {"person_id", "device_id", "sensor_id", "camera_id", "observation_id"}

    def extract(self, payload: Dict[str, Any]) -> Dict[str, List[str]]:
        result = {}
        if not isinstance(payload, dict):
            return result
        
        for key in self.KNOWN_KEYS:
            if key in payload:
                value = payload[key]
                if value is not None:
                    result[key] = [str(value)]
        return result
