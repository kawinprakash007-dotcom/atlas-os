import time
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple

from atlas_ui.backend.vision import config
from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.face_recognizer import FaceRecognizer
from atlas_ui.backend.vision.face_quality import validate_face_quality
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore, TemplateStatus, RECOGNIZER_ID

@dataclass
class FaceEnrollmentResult:
    """
    Result of a face enrollment pipeline run.
    """
    success: bool
    person_id: str
    samples_requested: int
    samples_captured: int
    samples_rejected: int
    error: Optional[str] = None
    reason: Optional[str] = None

class FaceEnrollmentService:
    """
    Coordinates face sample captures, quality validation, duplicates protection,
    and storage of face recognition templates for a user.
    """
    def __init__(
        self,
        detector: YOLOFaceDetector,
        recognizer: FaceRecognizer,
        store: FaceTemplateStore
    ):
        self.detector = detector
        self.recognizer = recognizer
        self.store = store
        self.session_cache = {}  # Maps person_id -> {"templates": [], "last_capture_time": 0.0, "samples_rejected": 0}

    def enroll_single_frame(self, person_id: str, frame: np.ndarray, overwrite: bool = False) -> FaceEnrollmentResult:
        if self.store.has_templates(person_id) and not overwrite:
            return FaceEnrollmentResult(
                success=False, person_id=person_id,
                samples_requested=config.ENROLL_SAMPLES_REQUIRED, samples_captured=0, samples_rejected=0,
                error="Enrollment exists", reason=f"Face templates already enrolled for person '{person_id}'."
            )

        if person_id not in self.session_cache:
            self.session_cache[person_id] = {"templates": [], "last_capture_time": 0.0, "samples_rejected": 0}
            
        session = self.session_cache[person_id]
        
        embedding, reject_reason, cap_time = self.process_frame(frame, session["templates"], session["last_capture_time"])
        
        if embedding is not None:
            session["templates"].append(embedding)
            session["last_capture_time"] = cap_time
        else:
            if reject_reason not in ["NO_FACE", "SAMPLE_TOO_QUICK"]:
                session["samples_rejected"] += 1
                
        dim = config.ENROLL_SAMPLES_REQUIRED
        
        if len(session["templates"]) < dim:
            # Still collecting
            return FaceEnrollmentResult(
                success=False, person_id=person_id,
                samples_requested=dim, samples_captured=len(session["templates"]), samples_rejected=session["samples_rejected"],
                error="Collecting", reason=reject_reason if embedding is None else None
            )
            
        # We have 5 samples, run consistency check
        templates = session["templates"]
        samples_rejected = session["samples_rejected"]
        
        # Clean up session
        del self.session_cache[person_id]
        
        expected_dim = len(templates[0])
        for i, t in enumerate(templates):
            if len(t) != expected_dim or not np.isfinite(t).all():
                return FaceEnrollmentResult(
                    success=False, person_id=person_id, samples_requested=dim, samples_captured=dim, samples_rejected=samples_rejected,
                    error="Invalid values", reason=f"Sample index {i} has invalid dimension or values."
                )

        self.store.save_templates(person_id, templates, recognizer=RECOGNIZER_ID, overwrite=overwrite)
        
        return FaceEnrollmentResult(
            success=True, person_id=person_id,
            samples_requested=dim, samples_captured=dim, samples_rejected=samples_rejected
        )

    def process_frame(
        self,
        frame: np.ndarray,
        existing_templates: List[List[float]],
        last_capture_time: float
    ) -> Tuple[Optional[List[float]], Optional[str], float]:
        """
        Processes a single frame for enrollment.
        Returns (embedding, reject_reason, capture_time).
        If embedding is not None, it was successfully accepted.
        """
        if frame is None or frame.size == 0:
            return None, "EMPTY_FRAME", last_capture_time

        # 1. YOLO face detection
        detection_res = self.detector.detect(frame)
        if detection_res.no_face:
            return None, "NO_FACE", last_capture_time
        if detection_res.multiple_faces:
            return None, "MULTIPLE_FACES", last_capture_time

        # Exactly one face
        face = detection_res.faces[0]
        bbox = face.bbox

        # 2. Quality validation
        quality_res = validate_face_quality(frame, bbox)
        if not quality_res.accepted:
            return None, f"QUALITY_REJECT: {quality_res.reason}", last_capture_time

        # 3. Interval check
        current_time = time.time()
        if current_time - last_capture_time < config.MIN_SAMPLE_INTERVAL_SECONDS:
            return None, "SAMPLE_TOO_QUICK", last_capture_time

        # 4. Crop and encode — pass full frame + bbox
        x1, y1, x2, y2 = bbox
        embed_res = self.recognizer.encode(frame, bbox)
        if not embed_res.success or embed_res.embedding is None:
            return None, f"ENCODE_FAIL: {embed_res.error}", last_capture_time

        embedding = embed_res.embedding

        # 5. Duplicate similarity check
        for existing in existing_templates:
            # Since templates are L2-normalized, cosine similarity is just the dot product
            similarity = sum(a * b for a, b in zip(embedding, existing))
            if similarity > config.MAX_DUPLICATE_SIMILARITY:
                return None, f"DUPLICATE_SAMPLE (similarity {similarity:.4f} > limit {config.MAX_DUPLICATE_SIMILARITY})", last_capture_time

        return embedding, None, current_time

    def enroll_from_camera(
        self,
        person_id: str,
        camera_index: int = 0,
        overwrite: bool = False,
        timeout_seconds: float = 30.0
    ) -> FaceEnrollmentResult:
        """
        Runs the full camera enrollment flow: captures frames, runs checks, and saves templates.
        """
        # Overwrite check before starting the camera
        if self.store.has_templates(person_id) and not overwrite:
            return FaceEnrollmentResult(
                success=False,
                person_id=person_id,
                samples_requested=config.ENROLL_SAMPLES_REQUIRED,
                samples_captured=0,
                samples_rejected=0,
                error="Enrollment exists",
                reason=f"Face templates already enrolled for person '{person_id}'."
            )

        print(f"[ENROLLMENT] Starting enrollment loop for '{person_id}'...", flush=True)

        templates: List[List[float]] = []
        last_capture_time = 0.0
        samples_rejected = 0
        start_time = time.time()

        try:
            with CameraManager(camera_index=camera_index) as camera:
                while len(templates) < config.ENROLL_SAMPLES_REQUIRED:
                    # Timeout check
                    if time.time() - start_time > timeout_seconds:
                        return FaceEnrollmentResult(
                            success=False,
                            person_id=person_id,
                            samples_requested=config.ENROLL_SAMPLES_REQUIRED,
                            samples_captured=len(templates),
                            samples_rejected=samples_rejected,
                            error="Timeout",
                            reason=f"Enrollment timed out after {timeout_seconds} seconds."
                        )

                    frame = camera.capture_frame()
                    embedding, reject_reason, cap_time = self.process_frame(frame, templates, last_capture_time)

                    if embedding is not None:
                        templates.append(embedding)
                        last_capture_time = cap_time
                        print(f"[ENROLLMENT] Captured sample {len(templates)}/{config.ENROLL_SAMPLES_REQUIRED}", flush=True)
                    else:
                        if reject_reason not in ["NO_FACE", "SAMPLE_TOO_QUICK"]:
                            samples_rejected += 1
                            print(f"[ENROLLMENT] Sample rejected: {reject_reason}", flush=True)
                    
                    time.sleep(0.03)  # Brief yield to CPU

            # Verification of final templates
            dim = config.ENROLL_SAMPLES_REQUIRED
            if len(templates) != dim:
                return FaceEnrollmentResult(
                    success=False,
                    person_id=person_id,
                    samples_requested=dim,
                    samples_captured=len(templates),
                    samples_rejected=samples_rejected,
                    error="Incomplete samples",
                    reason=f"Failed to capture {dim} valid samples."
                )

            # Check consistency of embeddings
            expected_dim = len(templates[0])
            for i, t in enumerate(templates):
                if len(t) != expected_dim:
                    return FaceEnrollmentResult(
                        success=False,
                        person_id=person_id,
                        samples_requested=dim,
                        samples_captured=len(templates),
                        samples_rejected=samples_rejected,
                        error="Inconsistent dimensions",
                        reason=f"Sample index {i} has inconsistent dimension."
                    )
                
                # Double check no NaNs/infs
                if not np.isfinite(t).all():
                    return FaceEnrollmentResult(
                        success=False,
                        person_id=person_id,
                        samples_requested=dim,
                        samples_captured=len(templates),
                        samples_rejected=samples_rejected,
                        error="Invalid values",
                        reason=f"Sample index {i} contains NaN/infinity."
                    )

            # Persist templates with recognizer metadata
            self.store.save_templates(
                person_id, templates,
                recognizer=RECOGNIZER_ID,
                overwrite=overwrite
            )
            return FaceEnrollmentResult(
                success=True,
                person_id=person_id,
                samples_requested=config.ENROLL_SAMPLES_REQUIRED,
                samples_captured=len(templates),
                samples_rejected=samples_rejected
            )

        except Exception as e:
            return FaceEnrollmentResult(
                success=False,
                person_id=person_id,
                samples_requested=config.ENROLL_SAMPLES_REQUIRED,
                samples_captured=len(templates),
                samples_rejected=samples_rejected,
                error="Runtime error",
                reason=str(e)
            )
