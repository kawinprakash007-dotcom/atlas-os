import time
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Device:
    device_id: str
    device_type: str
    capabilities: List[str] = field(default_factory=list)
    status: str = "ONLINE"
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.device_id:
            raise ValueError("device_id must be a non-empty string.")
        if not self.device_type:
            raise ValueError("device_type must be a non-empty string.")
        if self.status not in ("ONLINE", "STALE", "OFFLINE"):
            raise ValueError(f"Invalid device status: {self.status}")
