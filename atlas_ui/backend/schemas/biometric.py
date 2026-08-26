"""
Pydantic request/response schemas for the Phase 4A biometric API.

Follows the same BaseModel conventions used by auth.py and identity.py.
Actual embedding vectors are NEVER exposed in any response.
"""
from pydantic import BaseModel, Field
from typing import Optional
from atlas_ui.backend.schemas.location import GpsLocation


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

class BiometricStatusResponse(BaseModel):
    success: bool
    person_id: str
    enrolled: bool
    template_count: int
    embedding_dimension: int


# ---------------------------------------------------------------------------
# ENROLL
# ---------------------------------------------------------------------------

class BiometricEnrollRequest(BaseModel):
    person_id: str = Field(..., min_length=1, description="ATLAS person ID (e.g. ATLAS-P-88888888)")
    image_data: Optional[str] = None


class BiometricEnrollResponse(BaseModel):
    success: bool
    person_id: str
    samples_captured: int
    template_count: int
    embedding_dimension: int
    reason: str
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# VERIFY
# ---------------------------------------------------------------------------

class BiometricVerifyRequest(BaseModel):
    person_id: str = Field(..., min_length=1, description="ATLAS person ID to verify against")
    image_data: Optional[str] = Field(None, description="Base64 encoded image frame from frontend")
    gps_location: Optional[GpsLocation] = Field(None, description="Optional browser GPS coordinates")


class BiometricVerifyResponse(BaseModel):
    success: bool
    verified: bool
    person_id: str
    best_similarity: float
    threshold: float
    reason: str
    message: Optional[str] = None
    verification_token: Optional[str] = None


# ---------------------------------------------------------------------------
# RESET
# ---------------------------------------------------------------------------

class BiometricResetRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Operator username")
    password: str = Field(..., min_length=1, description="Operator password")


class BiometricResetResponse(BaseModel):
    success: bool
    message: str

