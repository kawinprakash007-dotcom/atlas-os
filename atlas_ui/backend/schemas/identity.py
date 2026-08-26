from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class PersonCreateRequest(BaseModel):
    display_name: str = Field(..., min_length=1)
    account_id: Optional[str] = None
    role: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class PersonResponse(BaseModel):
    atlas_person_id: str
    display_name: str
    account_id: Optional[str] = None
    role: Optional[str] = None
    status: str
    face_enrollment_status: str
    created_at: float
    updated_at: float
    metadata: Dict[str, Any]

class EnrollFaceRequest(BaseModel):
    biometric_raw_sample: str = Field(..., min_length=1)

class EnrollFaceResponse(BaseModel):
    success: bool
    face_enrollment_status: str
    message: str

class RevokeFaceResponse(BaseModel):
    success: bool
    face_enrollment_status: str
    message: str
