import urllib.request
import urllib.error
import json
from typing import Dict, Any

class VisionEventDispatcher:
    def __init__(self, target_url: str = "http://127.0.0.1:8000/api/v1/events"):
        self.target_url = target_url

    def dispatch(self, event_type: str, payload: Dict[str, Any]) -> bool:
        """
        Sends an event to the ATLAS OS core event receiver.
        """
        data = {
            "event_type": event_type,
            "source": payload.get("source", "ATLAS_VISION"),
            "payload": payload
        }
        
        req = urllib.request.Request(
            self.target_url,
            data=json.dumps(data).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        
        try:
            with urllib.request.urlopen(req, timeout=3) as res:
                return res.status == 200
        except Exception as e:
            # Drop the event if OS is unreachable or errors
            print(f"[VisionEventDispatcher] Failed to send {event_type}: {e}")
            return False
