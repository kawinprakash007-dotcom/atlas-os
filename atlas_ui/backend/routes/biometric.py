"""
Phase 4A / Phase 5 — Biometric API Router

Endpoints:
    GET  /api/v1/biometric/status/{person_id}   — check enrollment status
    POST /api/v1/biometric/enroll               — enroll a person's face
    POST /api/v1/biometric/verify               — verify a person's face

All camera-using operations are protected by a process-level threading.Lock so
that only one biometric camera session can be active at a time.

This router owns ONLY request validation, dependency resolution, and HTTP
response translation. All biometric logic lives in the vision service layer.

Phase 5 extension: on successful verification, a JPEG thumbnail (already
computed for the Person profile) is also written to the VerificationSnapshotStore
(best-effort; failures never affect the authentication result).
"""

import threading
import secrets
import base64
import cv2
import numpy as np
from typing import Optional

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from atlas_ui.backend.schemas.biometric import (
    BiometricStatusResponse,
    BiometricEnrollRequest,
    BiometricEnrollResponse,
    BiometricVerifyRequest,
    BiometricVerifyResponse,
    BiometricResetRequest,
    BiometricResetResponse,
)
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore, TemplateStatus
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.insightface_recognizer import InsightFaceRecognizer
from atlas_ui.backend.vision.face_enrollment_service import FaceEnrollmentService
from atlas_ui.backend.vision.face_verification_service import FaceVerificationService
from atlas_ui.backend.vision import config as vision_config
from atlas_ui.backend.models.snapshot import VerificationSnapshot

router = APIRouter(prefix="/api/v1/biometric", tags=["biometric"])

# Process-level camera lock — only one biometric operation may open the camera at a time
_camera_lock: threading.Lock = threading.Lock()

# Shared FaceTemplateStore (no camera involved — safe to share)
_face_store = FaceTemplateStore()

# Shared YOLO Face Detector, InsightFace Recognizer, Enrollment and Verification Services
_detector = YOLOFaceDetector(conf_threshold=0.50)
_recognizer = InsightFaceRecognizer()
_enroll_service = FaceEnrollmentService(_detector, _recognizer, _face_store)
_verify_service = FaceVerificationService(_detector, _recognizer, _face_store)


def _get_person_registry(request: Request):
    """Extract PersonRegistry from FastAPI app state."""
    return request.app.state.person_registry


def _get_audit(request: Request):
    """Extract AuthenticationAudit from FastAPI app state (best-effort)."""
    return getattr(request.app.state, "auth_audit", None)


def _log_event(request: Request, event_type: str, **kwargs) -> None:
    """Fire-and-forget audit log call; never raises so it cannot block the API."""
    try:
        audit = _get_audit(request)
        if audit:
            audit.log_attempt(event_type=event_type, **kwargs)
    except Exception as _ex:
        print(f"[BIOMETRIC AUDIT] Failed to write event {event_type}: {_ex}", flush=True)


# ---------------------------------------------------------------------------
# API 1 — STATUS
# ---------------------------------------------------------------------------

@router.get(
    "/status/{person_id}",
    response_model=BiometricStatusResponse,
    summary="Check biometric enrollment status for a person",
)
async def biometric_status(person_id: str, request: Request):
    """
    Returns whether a person has enrolled biometric templates.
    Does NOT open the camera. Reads from FaceTemplateStore only.
    """
    print(f"[BIOMETRIC API] Status requested for person={person_id}", flush=True)

    person_registry = _get_person_registry(request)

    # Validate person exists
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "person_id": person_id,
                "enrolled": False,
                "template_count": 0,
                "embedding_dimension": 0,
                "template_status": TemplateStatus.NOT_ENROLLED,
                "re_enrollment_required": False,
                "error": "PERSON_NOT_FOUND",
            },
        )

    tmpl_status = _face_store.get_template_status(person_id)
    enrolled = tmpl_status == TemplateStatus.ENROLLED
    re_enroll = tmpl_status in (
        TemplateStatus.LEGACY_TEMPLATE, TemplateStatus.RE_ENROLLMENT_REQUIRED
    )

    if not _face_store.has_templates(person_id):
        return BiometricStatusResponse(
            success=True,
            person_id=person_id,
            enrolled=False,
            template_count=0,
            embedding_dimension=0,
        )

    if re_enroll:
        templates = _face_store.get_templates(person_id)
        template_count = len(templates) if templates else 0
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "person_id": person_id,
                "enrolled": False,
                "template_count": template_count,
                "embedding_dimension": _face_store.get_embedding_dimension(person_id) or 0,
                "template_status": str(tmpl_status),
                "re_enrollment_required": True,
                "recognizer": _face_store.get_recognizer(person_id),
            },
        )

    templates = _face_store.get_templates(person_id)
    template_count = len(templates)
    embedding_dimension = len(templates[0]) if templates else 0

    print(
        f"[BIOMETRIC API] Status for {person_id}: enrolled=True "
        f"templates={template_count} dim={embedding_dimension}",
        flush=True,
    )
    return BiometricStatusResponse(
        success=True,
        person_id=person_id,
        enrolled=True,
        template_count=template_count,
        embedding_dimension=embedding_dimension,
    )


# ---------------------------------------------------------------------------
# API 2 — ENROLL
# ---------------------------------------------------------------------------

@router.post(
    "/enroll",
    response_model=BiometricEnrollResponse,
    status_code=status.HTTP_200_OK,
    summary="Enroll a person's face using the live camera",
)
async def biometric_enroll(body: BiometricEnrollRequest, request: Request):
    """
    Captures 5 ArcFace face samples from the live camera and persists them
    as biometric templates for the given person.

    Returns ALREADY_ENROLLED if templates already exist for the person.
    Returns CAMERA_BUSY if another biometric operation holds the camera lock.
    Does NOT overwrite existing valid templates on partial failure.
    """
    person_id = body.person_id
    print(f"[BIOMETRIC API] Enrollment requested for person={person_id}", flush=True)

    person_registry = _get_person_registry(request)

    # 1. Validate person exists
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "person_id": person_id,
                "samples_captured": 0,
                "template_count": 0,
                "embedding_dimension": 0,
                "reason": "PERSON_NOT_FOUND",
                "message": f"Person '{person_id}' does not exist in the registry.",
            },
        )

    # Log FACE_ENROLLMENT_STARTED
    _ip = request.client.host if request.client else None
    _ua = request.headers.get("user-agent")
    _log_event(request, "FACE_ENROLLMENT_STARTED",
               person_id=person_id,
               account_id=person.account_id,
               access_result="SUCCESS",
               ip_address=_ip,
               device_info=_ua)

    # 2. Check already enrolled — but treat LEGACY as needing re-enrollment (not blocked)
    tmpl_status = _face_store.get_template_status(person_id)
    if tmpl_status == TemplateStatus.ENROLLED:
        existing_count = len(_face_store.get_templates(person_id))
        print(
            f"[BIOMETRIC API] Person {person_id} already has {existing_count} valid templates.",
            flush=True,
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "person_id": person_id,
                "samples_captured": 0,
                "template_count": existing_count,
                "embedding_dimension": 0,
                "reason": "ALREADY_ENROLLED",
                "message": (
                    f"Person '{person_id}' already has {existing_count} biometric "
                    f"templates enrolled. Revoke first to re-enroll."
                ),
            },
        )

    # Legacy templates: auto-clear them so fresh enrollment can proceed
    if tmpl_status in (TemplateStatus.LEGACY_TEMPLATE, TemplateStatus.RE_ENROLLMENT_REQUIRED):
        print(
            f"[BIOMETRIC API] Clearing legacy/incompatible templates for {person_id} before re-enrollment.",
            flush=True,
        )
        _face_store.remove_templates(person_id)

    # 3. Camera concurrency guard
    print(f"[BIOMETRIC API] Acquiring camera lock for enrollment...", flush=True)
    acquired = _camera_lock.acquire(blocking=False)
    if not acquired:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "person_id": person_id,
                "samples_captured": 0,
                "template_count": 0,
                "embedding_dimension": 0,
                "reason": "CAMERA_BUSY",
                "message": "Another biometric operation is currently using the camera.",
            },
        )

    print(f"[BIOMETRIC API] Camera lock acquired. Starting enrollment.", flush=True)
    try:
        if FaceEnrollmentService != _enroll_service.__class__:
            enroll_service = FaceEnrollmentService(None, None, _face_store)
        else:
            enroll_service = _enroll_service

        print(f"[BIOMETRIC API] Starting enrollment for person={person_id}", flush=True)
        if body.image_data:
            img_b64 = body.image_data
            if "," in img_b64:
                img_b64 = img_b64.split(",")[1]
            img_bytes = base64.b64decode(img_b64)
            img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            result = enroll_service.enroll_single_frame(person_id=person_id, frame=frame, overwrite=False)
        else:
            result = enroll_service.enroll_from_camera(
                person_id=person_id,
                camera_index=vision_config.FACE_CAMERA_INDEX,
                overwrite=False,
                timeout_seconds=30.0,
            )
    except Exception as exc:
        print(f"[BIOMETRIC API] Enrollment exception: {exc}", flush=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "person_id": person_id,
                "samples_captured": 0,
                "template_count": 0,
                "embedding_dimension": 0,
                "reason": "CAMERA_UNAVAILABLE",
                "message": str(exc),
            },
        )
    finally:
        _camera_lock.release()
        print(f"[BIOMETRIC API] Camera lock released after enrollment.", flush=True)

    if not result.success:
        if result.error == "Collecting":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "success": False,
                    "error": "Collecting",
                    "person_id": person_id,
                    "samples_captured": result.samples_captured,
                    "samples_requested": result.samples_requested,
                    "template_count": 0,
                    "embedding_dimension": 0,
                    "reason": result.reason or "",
                    "message": result.reason or "",
                }
            )
        reason = _map_enroll_reason(result.reason or result.error or "ENROLLMENT_FAILED")
        print(
            f"[BIOMETRIC API] Enrollment failed for {person_id}: "
            f"reason={reason} captured={result.samples_captured}",
            flush=True,
        )
        http_status = _enroll_error_status(reason)
        return JSONResponse(
            status_code=http_status,
            content={
                "success": False,
                "person_id": person_id,
                "samples_captured": result.samples_captured,
                "template_count": 0,
                "embedding_dimension": 0,
                "reason": reason,
                "message": result.reason,
            },
        )

    # Reload verification
    reloaded = _face_store.get_templates(person_id)
    template_count = len(reloaded)
    dim = len(reloaded[0]) if reloaded else 0

    # Update person's biometric enrollment status in PersonRegistry
    try:
        import time as _time
        person_registry = _get_person_registry(request)
        person_registry.update_person(
            person_id,
            face_enrollment_status="ENROLLED",
            enrolled_at=_time.time(),
            template_count=template_count,
        )
    except Exception as e:
        print(f"[BIOMETRIC API] Failed to update person status in PersonRegistry: {e}", flush=True)

    # Log FACE_ENROLLMENT_COMPLETED
    _log_event(request, "FACE_ENROLLMENT_COMPLETED",
               person_id=person_id,
               account_id=person.account_id if person else None,
               access_result="SUCCESS",
               ip_address=_ip,
               device_info=_ua,
               metadata={"template_count": template_count, "embedding_dim": dim})

    print(
        f"[BIOMETRIC API] Enrollment completed for {person_id}: "
        f"templates={template_count} dim={dim}",
        flush=True,
    )
    
    # Phase IM3: Synchronize successful face enrollment to IdentityMemory
    identity_memory = getattr(request.app.state, "identity_memory", None)
    if identity_memory:
        identity_memory.mark_face_enrolled(person_id)
        
    return BiometricEnrollResponse(
        success=True,
        person_id=person_id,
        samples_captured=result.samples_captured,
        template_count=template_count,
        embedding_dimension=dim,
        reason="ENROLLMENT_COMPLETED",
        message=f"Successfully enrolled {template_count} biometric templates for '{person_id}'.",
    )


# ---------------------------------------------------------------------------
# API 3 — VERIFY
# ---------------------------------------------------------------------------

@router.post(
    "/verify",
    response_model=BiometricVerifyResponse,
    summary="Verify a person's face against enrolled templates",
)
async def biometric_verify(body: BiometricVerifyRequest, request: Request):
    """
    Opens the live camera and verifies the presented face against the enrolled
    templates for the given person.

    A failed match is NOT a server error (HTTP 200 with verified=False).
    Returns CAMERA_BUSY if another biometric operation holds the camera lock.
    Always releases the camera even on exceptions (fail-closed).
    """
    person_id = body.person_id
    print(f"[BIOMETRIC API] Verification requested for person={person_id}", flush=True)

    person_registry = _get_person_registry(request)

    # 1. Validate person
    person = person_registry.get_person(person_id)
    if person is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "verified": False,
                "person_id": person_id,
                "best_similarity": 0.0,
                "threshold": vision_config.FACE_MATCH_THRESHOLD,
                "reason": "PERSON_NOT_FOUND",
                "message": f"Person '{person_id}' does not exist in the registry.",
            },
        )

    # Log BIOMETRIC_VERIFICATION_STARTED
    _v_ip = request.client.host if request.client else None
    _v_ua = request.headers.get("user-agent")
    # Extract optional GPS location submitted by the browser client
    _v_gps = body.gps_location
    _v_gps_lat = _v_gps.latitude if _v_gps else None
    _v_gps_lon = _v_gps.longitude if _v_gps else None
    _v_gps_acc = _v_gps.accuracy if _v_gps else None
    _v_loc_perm = _v_gps.status if _v_gps else None
    _log_event(request, "BIOMETRIC_VERIFICATION_STARTED",
               person_id=person_id,
               account_id=person.account_id,
               access_result="SUCCESS",
               ip_address=_v_ip,
               device_info=_v_ua)

    # 2. Validate enrollment
    if not _face_store.has_templates(person_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "verified": False,
                "person_id": person_id,
                "best_similarity": 0.0,
                "threshold": vision_config.FACE_MATCH_THRESHOLD,
                "reason": "NO_BIOMETRIC_ENROLLMENT",
                "message": f"No biometric templates enrolled for '{person_id}'.",
            },
        )

    # 3. Camera concurrency guard
    print(f"[BIOMETRIC API] Acquiring camera lock for verification...", flush=True)
    acquired = _camera_lock.acquire(blocking=False)
    if not acquired:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "verified": False,
                "person_id": person_id,
                "best_similarity": 0.0,
                "threshold": vision_config.FACE_MATCH_THRESHOLD,
                "reason": "CAMERA_BUSY",
                "message": "Another biometric operation is currently using the camera.",
            },
        )

    print(f"[BIOMETRIC API] Camera lock acquired. Starting verification.", flush=True)
    try:
        if FaceVerificationService != _verify_service.__class__:
            verify_service = FaceVerificationService(None, None, _face_store)
        else:
            verify_service = _verify_service

        if body.image_data:
            # Decode base64 image data
            # Data usually comes as: data:image/jpeg;base64,/9j/4AAQSkZ...
            img_b64 = body.image_data
            if "," in img_b64:
                img_b64 = img_b64.split(",")[1]
            img_bytes = base64.b64decode(img_b64)
            img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
            result = verify_service.verify_frame(
                person_id=person_id,
                frame=frame,
                frame_id=1,
                verbose=False
            )
        else:
            result = verify_service.verify_from_camera(
                person_id=person_id,
                camera_index=vision_config.FACE_CAMERA_INDEX,
                timeout_seconds=10.0,
                verbose=False,
            )
    except Exception as exc:
        print(f"[BIOMETRIC API] Verification exception: {exc}", flush=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "verified": False,
                "person_id": person_id,
                "best_similarity": 0.0,
                "threshold": vision_config.FACE_MATCH_THRESHOLD,
                "reason": "CAMERA_UNAVAILABLE",
                "message": str(exc),
            },
        )
    finally:
        _camera_lock.release()
        print(f"[BIOMETRIC API] Camera lock released after verification.", flush=True)

    print(
        f"[BIOMETRIC API] Verification result for {person_id}: "
        f"verified={result.verified} similarity={result.best_similarity:.4f} "
        f"reason={result.reason}",
        flush=True,
    )

    # A failed match is a normal application outcome, not a server error
    reason = _map_verify_reason(result.reason or "INTERNAL_ERROR")
    re_enrollment = result.reason == "RE_ENROLLMENT_REQUIRED"
    if re_enrollment:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "verified": False,
                "person_id": person_id,
                "best_similarity": 0.0,
                "threshold": vision_config.FACE_MATCH_THRESHOLD,
                "reason": "RE_ENROLLMENT_REQUIRED",
                "message": "Enrolled templates are from an old recognition model. Re-enrollment required.",
                "re_enrollment_required": True,
            },
        )

    verification_token = None
    if result.verified:
        verified_status = True
        verification_token = secrets.token_hex(32)
        if hasattr(request.app.state, "auth_service"):
            request.app.state.auth_service.register_biometric_success(person_id, verification_token)
        # Log BIOMETRIC_VERIFICATION_SUCCESS
        _log_event(request, "BIOMETRIC_VERIFICATION_SUCCESS",
                   person_id=person_id,
                   account_id=person.account_id if person else None,
                   access_result="SUCCESS",
                   face_verified=True,
                   biometric_score=round(result.best_similarity, 6),
                   verification_result=reason,
                   ip_address=_v_ip,
                   device_info=_v_ua,
                   gps_latitude=_v_gps_lat,
                   gps_longitude=_v_gps_lon,
                   gps_accuracy=_v_gps_acc)
    else:
        verified_status = result.verified
        # Log BIOMETRIC_VERIFICATION_FAILED
        _log_event(request, "BIOMETRIC_VERIFICATION_FAILED",
                   person_id=person_id,
                   account_id=person.account_id if person else None,
                   access_result="FAILURE",
                   face_verified=False,
                   biometric_score=round(result.best_similarity, 6),
                   verification_result=reason,
                   failure_category=reason,
                   ip_address=_v_ip,
                   device_info=_v_ua,
                   gps_latitude=_v_gps_lat,
                   gps_longitude=_v_gps_lon,
                   gps_accuracy=_v_gps_acc)

    # Phase 5: thumbnail URI shared between Person profile update and snapshot store.
    # Initialised to None; set inside the inner try if image decode succeeds.
    _snap_thumbnail: Optional[str] = None

    # Record verification evidence on Person profile
    try:
        import time as _time
        _pr = _get_person_registry(request)
        evidence_updates = {
            "last_biometric_verification": _time.time(),
            "last_verification_status": reason,
            "latest_verification_timestamp": _time.time(),
            "latest_verification_result": reason,
            "latest_verification_score": round(result.best_similarity, 6),
            # GPS from biometric verification event
            "gps_latitude": _v_gps_lat,
            "gps_longitude": _v_gps_lon,
            "gps_accuracy": _v_gps_acc,
            "location_permission": _v_loc_perm,
        }
        # Store a compact JPEG thumbnail snapshot (max 120px wide) without logging it
        if body.image_data:
            try:
                _snapshot_b64 = body.image_data
                if "," in _snapshot_b64:
                    _prefix, _snapshot_b64 = _snapshot_b64.split(",", 1)
                else:
                    _prefix = "data:image/jpeg;base64"
                _img_bytes = base64.b64decode(_snapshot_b64)
                _img_arr = np.frombuffer(_img_bytes, dtype=np.uint8)
                _thumb = cv2.imdecode(_img_arr, cv2.IMREAD_COLOR)
                if _thumb is not None:
                    _h, _w = _thumb.shape[:2]
                    _scale = 120.0 / max(_w, 1)
                    if _scale < 1.0:
                        _thumb = cv2.resize(_thumb, (int(_w * _scale), int(_h * _scale)))
                    _, _buf = cv2.imencode(".jpg", _thumb, [cv2.IMWRITE_JPEG_QUALITY, 60])
                    _thumb_b64 = base64.b64encode(_buf).decode()
                    _snap_thumbnail = f"data:image/jpeg;base64,{_thumb_b64}"   # Phase 5: shared ref
                    evidence_updates["latest_verification_snapshot"] = _snap_thumbnail
            except Exception:
                pass  # Snapshot is best-effort; never block verification
        _pr.update_person(person_id, **evidence_updates)
    except Exception as _e:
        print(f"[BIOMETRIC API] Failed to record verification evidence: {_e}", flush=True)

    # ---------------------------------------------------------------------------
    # Phase 5 — Write to VerificationSnapshotStore (successful verifications only)
    # ---------------------------------------------------------------------------
    # Wrapped in try/except so any store failure is completely non-fatal.
    # _snap_thumbnail is None when the request used camera-direct mode (no image_data).
    if result.verified:
        try:
            _snap_store = getattr(request.app.state, "snapshot_store", None)
            if _snap_store is not None:
                import time as _t5
                # Extract session ID from request headers (may be absent pre-login)
                _auth_hdr = request.headers.get("Authorization", "")
                _sess_id_snap = (
                    _auth_hdr[7:].strip() if _auth_hdr.startswith("Bearer ") else
                    request.headers.get("x-session-id") or
                    request.cookies.get("session_id") or
                    None
                )
                _snap_store.store(VerificationSnapshot(
                    person_id=person_id,
                    account_id=person.account_id if person else None,
                    session_id=_sess_id_snap,
                    timestamp=_t5.time(),
                    result=reason,
                    score=round(result.best_similarity, 6),
                    thumbnail_b64=_snap_thumbnail,
                ))
        except Exception as _snap_err:
            print(
                f"[BIOMETRIC API] Snapshot store write failed (non-fatal): {_snap_err}",
                flush=True,
            )

    return BiometricVerifyResponse(
        success=True,
        verified=verified_status,
        person_id=person_id,
        best_similarity=round(result.best_similarity, 6),
        threshold=vision_config.FACE_MATCH_THRESHOLD,
        reason=reason,
        message=result.reason,
        verification_token=verification_token
    )


# ---------------------------------------------------------------------------
# Internal reason mappers
# ---------------------------------------------------------------------------

def _map_enroll_reason(raw: Optional[str]) -> str:
    if raw is None:
        return "ENROLLMENT_FAILED"
    r = raw.upper()
    if "CAMERA" in r or "OPEN" in r:
        return "CAMERA_UNAVAILABLE"
    if "NO_FACE" in r:
        return "NO_FACE"
    if "MULTIPLE" in r:
        return "MULTIPLE_FACES"
    if "TIMEOUT" in r or "INSUFFICIENT" in r or "REQUIRED" in r:
        return "INSUFFICIENT_VALID_SAMPLES"
    if "EMBED" in r or "ENCODE" in r:
        return "EMBEDDING_FAILURE"
    if "PERSIST" in r or "SAVE" in r or "WRITE" in r:
        return "PERSISTENCE_FAILURE"
    return "ENROLLMENT_FAILED"


def _map_verify_reason(raw: Optional[str]) -> str:
    if raw is None:
        return "INTERNAL_ERROR"
    r = raw.upper()
    if "RE_ENROLLMENT" in r:
        return "RE_ENROLLMENT_REQUIRED"
    if "MATCH" in r and "NO_MATCH" not in r:
        return "MATCH"
    if "NO_MATCH" in r:
        return "NO_MATCH"
    if "NO_FACE" in r:
        return "NO_FACE"
    if "MULTIPLE" in r:
        return "MULTIPLE_FACES"
    if "CAMERA" in r:
        return "CAMERA_UNAVAILABLE"
    if "EMBED" in r or "ENCODE" in r:
        return "EMBEDDING_FAILURE"
    if "ENROLL" in r:
        return "NO_BIOMETRIC_ENROLLMENT"
    return "INTERNAL_ERROR"


def _enroll_error_status(reason: str) -> int:
    mapping = {
        "CAMERA_UNAVAILABLE": status.HTTP_503_SERVICE_UNAVAILABLE,
        "NO_FACE": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "MULTIPLE_FACES": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INSUFFICIENT_VALID_SAMPLES": status.HTTP_422_UNPROCESSABLE_CONTENT,
        "EMBEDDING_FAILURE": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "PERSISTENCE_FAILURE": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return mapping.get(reason, status.HTTP_500_INTERNAL_SERVER_ERROR)


@router.post(
    "/reset",
    response_model=BiometricResetResponse,
    summary="Reset a person's biometric templates by verifying credentials",
)
async def biometric_reset(body: BiometricResetRequest, request: Request):
    """
    Resets/revokes biometric templates for the user after validating credentials.
    """
    username = body.username
    password = body.password
    print(f"[BIOMETRIC API] Reset requested for user={username}", flush=True)

    credential_verifier = request.app.state.credential_verifier
    account_registry = request.app.state.account_registry
    person_registry = _get_person_registry(request)

    try:
        # Verify credentials first (protect against unauthorized resets)
        verified_acc = credential_verifier.verify_credentials(username, password)
    except ValueError as e:
        print(f"[BIOMETRIC API] Reset failed: invalid credentials for {username}: {e}", flush=True)
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"success": False, "message": "Invalid operator credentials."},
        )

    # Resolve person corresponding to account
    person = person_registry.get_person_by_account(verified_acc.account_id)
    if not person:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "No linked operator profile found."},
        )

    person_id = person.atlas_person_id

    # Remove face templates
    _face_store.remove_templates(person_id)
    
    # Update enrollment status in PersonRegistry
    person_registry.update_person(person_id, face_enrollment_status="NOT_ENROLLED")

    # Log FACE_ENROLLMENT_RESET
    _reset_ip = request.client.host if request.client else None
    _reset_ua = request.headers.get("user-agent")
    _log_event(request, "FACE_ENROLLMENT_RESET",
               person_id=person_id,
               account_id=person.account_id,
               access_result="SUCCESS",
               ip_address=_reset_ip,
               device_info=_reset_ua)

    print(f"[BIOMETRIC API] Biometrics successfully reset for person={person_id}", flush=True)
    return BiometricResetResponse(
        success=True,
        message="Biometric profile has been successfully reset. Please log in to configure new templates."
    )

