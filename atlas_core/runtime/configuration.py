from dataclasses import dataclass, field
from typing import Any, Dict

@dataclass
class ATLASConfiguration:
    db_path: str = "" # Default empty string so the runtime handles it intelligently
    enable_escalation: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    device_stale_threshold: float = 60.0
    device_offline_threshold: float = 120.0
