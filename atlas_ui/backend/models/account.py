from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Account:
    account_id: str
    username: str
    password_hash: str
    password_salt: str
    role: str
    enabled: bool
    created_at: float
    metadata: Dict[str, Any] = field(default_factory=dict)
