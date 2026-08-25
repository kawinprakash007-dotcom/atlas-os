import uuid
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

@dataclass
class Event:
    source: str
    event_type: str
    priority: str
    payload: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.source:
            raise ValueError("Event source is required.")
        if not self.event_type:
            raise ValueError("Event type is required.")
        if self.priority not in ["low", "normal", "high", "critical"]:
            raise ValueError(f"Invalid priority: {self.priority}. Must be low, normal, high, or critical.")
        if not isinstance(self.payload, dict):
            raise ValueError("Payload must be a dictionary.")
