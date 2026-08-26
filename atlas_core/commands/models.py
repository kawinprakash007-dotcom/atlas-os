import copy
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class DeviceCommand:
    command_id: str
    target_device: str
    command_type: str
    payload: Dict[str, Any]
    created_at: float

    status: str = "PENDING"

    dispatched_at: Optional[float] = None
    acknowledged_at: Optional[float] = None
    completed_at: Optional[float] = None

    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        # Deep-copy mutable payload/metadata to protect internal state
        self.payload = copy.deepcopy(self.payload) if self.payload is not None else {}
        self.metadata = copy.deepcopy(self.metadata) if self.metadata is not None else {}
