"""
Shared GPS location schema used by the login and biometric verify endpoints.

All fields are optional so callers that do not send location data remain
compatible.  The 'status' field carries the browser permission outcome:

    granted     — coordinates were successfully captured
    denied      — user declined the permission prompt
    unavailable — browser could not determine position (no GPS, timeout, etc.)
    unsupported — navigator.geolocation is not available in this browser

The backend never requires this object to be present; it is always safe to
omit it entirely or send it with all-null fields.
"""
from pydantic import BaseModel
from typing import Optional


class GpsLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None       # metres
    timestamp: Optional[float] = None      # Unix epoch (ms from browser, normalised to seconds server-side)
    status: Optional[str] = None           # granted | denied | unavailable | unsupported
