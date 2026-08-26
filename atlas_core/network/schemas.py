from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, ValidationError, field_validator

class ContractValidationError(ValueError):
    """Raised when an incoming message violates the ATLAS Vision API contract."""
    pass

class VisionEvent(BaseModel):
    event_type: str = Field(..., min_length=1)
    source: str
    payload: Optional[Dict[str, Any]] = None

    model_config = {
        "frozen": True,
        "extra": "allow"  # Allow flat arbitrary fields alongside event_type
    }

    @field_validator("source", mode="before")
    @classmethod
    def validate_source(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("source must be a string")
        if not v.strip():
            raise ValueError("source must not be empty or whitespace-only")
        return v

def validate_event(data: Any) -> VisionEvent:
    """
    Validates that incoming data is a dictionary and contains a valid event_type and source.
    Raises ContractValidationError if validation fails.
    """
    if not isinstance(data, dict):
        raise ContractValidationError("Incoming event must be a JSON object (dictionary).")
    try:
        return VisionEvent(**data)
    except ValidationError as e:
        # Custom nice error message matching expected strings
        errors = e.errors()
        for err in errors:
            loc = err.get("loc", ())
            if "source" in loc:
                msg = err.get("msg", "")
                if err.get("type") == "missing":
                    raise ContractValidationError("Schema validation failed: Missing top-level event source.") from e
                elif "whitespace" in msg or "empty" in msg or "value_error" in msg:
                    raise ContractValidationError("Schema validation failed: source must not be empty or whitespace-only.") from e
        raise ContractValidationError(f"Schema validation failed: {str(e)}") from e
    except Exception as e:
        raise ContractValidationError(f"Schema validation failed: {str(e)}") from e
