from dataclasses import dataclass, field
from typing import List

@dataclass
class Session:
    session_id: str
    account_id: str
    role: str
    created_at: float
    expires_at: float
    last_activity: float
    is_active: bool = True
    permissions: List[str] = field(default_factory=list)
