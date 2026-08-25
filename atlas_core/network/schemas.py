from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class ContractValidationError(ValueError):
    """Raised when an incoming message violates the ATLAS Vision API contract."""
    pass

class VisionEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    payload: Optional[Dict[str, Any]] = None

    model_config = {
        "frozen": True,
        "extra": "allow"  # Allow flat arbitrary fields alongside event_type
    }

def validate_event(data: Any) -> VisionEvent:
    """
    Validates that incoming data is a dictionary and contains a valid event_type.
    Raises ContractValidationError if validation fails.
    """
    if not isinstance(data, dict):
        raise ContractValidationError("Incoming event must be a JSON object (dictionary).")
    try:
        return VisionEvent(**data)
    except Exception as e:
        raise ContractValidationError(f"Schema validation failed: {str(e)}") from e
