from pydantic import BaseModel, Field
from typing import Optional, List
from atlas_ui.backend.schemas.location import GpsLocation

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    biometric_input: Optional[str] = None
    gps_location: Optional[GpsLocation] = None

class LoginResponse(BaseModel):
    authenticated: bool
    biometric_required: Optional[bool] = False
    person_id: Optional[str] = None
    role: Optional[str] = None
    permissions: List[str] = []
    session_id: Optional[str] = None
    expires_at: Optional[float] = None
    message: str
