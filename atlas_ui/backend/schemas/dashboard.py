from pydantic import BaseModel
from typing import Dict, Any, List, Optional

class DashboardDataResponse(BaseModel):
    role: str
    person_id: Optional[str] = None
    system_status: str
    devices: List[Dict[str, Any]]
    recent_events: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    admin_controls: Optional[Dict[str, Any]] = None
