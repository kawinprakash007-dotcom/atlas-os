"""
VerificationSnapshot — immutable record of a single successful biometric verification.

Stored by VerificationSnapshotStore; never written to disk (in-memory, same lifecycle
as AuthenticationAudit).  Embedding vectors are NEVER stored here.
"""
import uuid
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class VerificationSnapshot:
    """
    Captures the outcome and supporting evidence of one successful biometric
    verification event.

    Fields
    ------
    snapshot_id       Unique UUID for this record (auto-generated).
    person_id         ATLAS person identifier.
    account_id        Account linked to this person (may be None).
    session_id        Session token present at verify time, if any.
                      Note: in the standard flow the session is created AFTER
                      biometric success, so this is often None or the pre-auth
                      bearer value.
    timestamp         Unix epoch seconds when the snapshot was recorded.
    result            Mapped verification reason string (MATCH | NO_MATCH | …).
    score             Cosine similarity score in [0.0, 1.0].
    thumbnail_b64     data:image/jpeg;base64,… thumbnail (120 px wide, JPEG 60 %).
                      None when the verify call used camera-direct mode (no
                      image_data in the request body).
    """
    person_id:     str
    result:        str
    score:         float
    snapshot_id:   str              = field(default_factory=lambda: str(uuid.uuid4()))
    account_id:    Optional[str]    = None
    session_id:    Optional[str]    = None
    timestamp:     float            = field(default_factory=time.time)
    thumbnail_b64: Optional[str]    = None
