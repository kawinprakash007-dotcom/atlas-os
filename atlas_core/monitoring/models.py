from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class EventTrace:
    trace_id: str
    event_type: str
    source: str
    received_at: float

    status: str = "RECEIVED"

    validated: bool = False
    device_verified: bool = False

    verdict: Optional[str] = None
    action_status: Optional[str] = None

    completed_at: Optional[float] = None
    error: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)
