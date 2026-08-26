import time
import hashlib
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional

from atlas_ui.backend.vision import config
from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.face_recognizer import FaceRecognizer
from atlas_ui.backend.vision.face_quality import validate_face_quality
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore, TemplateStatus
from atlas_ui.backend.vision.cosine_similarity import cosine_similarity, best_cosine_similarity, CosineSimilarityError


@dataclass
class FaceVerificationResult:
    """
    Outcome of a face verification attempt.
    """
    verified: bool
    person_id: str
    best_similarity: float
    matched_template_index: int
    faces_detected: int
    reason: Optional[str] = None
    error: Optional[str] = None


def _frame_fingerprint(frame: np.ndarray) -> str:
    """MD5 of the raw byte content of the frame — cheap, deterministic."""
    return hashlib.md5(frame.tobytes()).hexdigest()[:12]


def _crop_stats(crop: np.ndarray) -> dict:
    """Return lightweight statistics of a face crop for fingerprinting."""
    return {
        "mean": float(np.mean(crop)),
        "std":  float(np.std(crop)),
        "fp":   hashlib.md5(crop.tobytes()).hexdigest()[:12],
    }


def _embedding_stats(embedding: List[float]) -> dict:
    """Return lightweight statistics of an embedding for fingerprinting."""
    arr = np.array(embedding)
    return {
        "mean":  float(np.mean(arr)),
        "std":   float(np.std(arr)),
        "norm":  float(np.linalg.norm(arr)),
        "fp":    hashlib.md5(arr.tobytes()).hexdigest()[:12],
    }


class FaceVerificationService:
    """
    Performs identity verification by matching live camera frame embeddings
    against the stored templates database using cosine similarity.
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

    # ------------------------------------------------------------------
    # Single-frame verification
    # ------------------------------------------------------------------

    def verify_frame(
        self,
        person_id: str,
        frame: np.ndarray,
        frame_id: int = 0,
        verbose: bool = False,
    ) -> FaceVerificationResult:
        """
        Verifies a single image frame against the enrolled templates for the requested person_id.
        Strict face-count gating: no embedding generated unless EXACTLY one face is present.
        """
        # 0. Basic checks
        if frame is None or frame.size == 0:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="EMPTY_FRAME"
            )

        if verbose:
            fp = _frame_fingerprint(frame)
            print(
                f"[FRAME] id={frame_id}  shape={frame.shape}  "
                f"fingerprint={fp}", flush=True
            )

        # 1. Load enrolled templates — check status first
        status = self.store.get_template_status(person_id)

        if status == TemplateStatus.NOT_ENROLLED:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="NO_ENROLLMENT"
            )

        if status in (TemplateStatus.LEGACY_TEMPLATE, TemplateStatus.RE_ENROLLMENT_REQUIRED):
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="RE_ENROLLMENT_REQUIRED"
            )

        if status == TemplateStatus.CORRUPTED_TEMPLATE:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="CORRUPTED_TEMPLATE"
            )

        templates = self.store.get_templates(person_id)
        if not templates:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="NO_ENROLLMENT_TEMPLATES"
            )

        # 2. YOLO face detection
        detection_res = self.detector.detect(frame)
        face_count = detection_res.face_count

        if verbose:
            print(
                f"[DETECTION] frame_id={frame_id}  face_count={face_count}",
                flush=True
            )

        # === STRICT FACE-COUNT GATE ===
        # NO embedding is generated unless exactly one face is present.
        if face_count == 0:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="NO_FACE"
            )

        if face_count >= 2:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=face_count, reason="MULTIPLE_FACES"
            )

        # Exactly one face — continue
        face = detection_res.faces[0]
        bbox = face.bbox
        x1, y1, x2, y2 = bbox

        if verbose:
            print(
                f"[SELECTED FACE] frame_id={frame_id}  "
                f"bbox={bbox}  width={x2-x1}  height={y2-y1}  "
                f"conf={face.confidence:.4f}", flush=True
            )

        # 3. Quality check
        quality_res = validate_face_quality(frame, bbox)
        if not quality_res.accepted:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=1, reason=f"QUALITY_REJECT: {quality_res.reason}"
            )

        # 4. Crop and fingerprint
        crop = frame[y1:y2, x1:x2]
        if verbose:
            cs = _crop_stats(crop)
            print(
                f"[FACE CROP] frame_id={frame_id}  shape={crop.shape}  "
                f"mean={cs['mean']:.2f}  std={cs['std']:.2f}  "
                f"fingerprint={cs['fp']}", flush=True
            )

        # 5. Encode — pass full frame + bbox (InsightFace needs full frame for alignment)
        embed_res = self.recognizer.encode(frame, bbox)
        if not embed_res.success or embed_res.embedding is None:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=1, reason=f"ENCODE_FAIL: {embed_res.error}"
            )

        probe = embed_res.embedding

        # Embed stats for verbose
        if verbose:
            arr_p = np.array(probe)
            es = _embedding_stats(probe)
            print(
                f"[EMBEDDING] frame_id={frame_id}  dim={embed_res.embedding_dimension}  "
                f"norm={es['norm']:.6f}  mean={es['mean']:.6f}  "
                f"std={es['std']:.6f}  fingerprint={es['fp']}", flush=True
            )
            if verbose and templates:
                # Per-template breakdown
                for tidx, tmpl in enumerate(templates):
                    try:
                        ts = cosine_similarity(probe, tmpl)
                        print(f"  Template {tidx+1}: {ts:.4f}", flush=True)
                    except CosineSimilarityError as e:
                        print(f"  Template {tidx+1}: ERROR ({e})", flush=True)

        # Sanity: embedding must be finite and unit norm
        arr = np.array(probe)
        if not np.isfinite(arr).all():
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=1, reason="ENCODE_FAIL: embedding non-finite"
            )
        norm = float(np.linalg.norm(arr))
        if norm < 0.5 or norm > 2.0:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=1, reason=f"ENCODE_FAIL: abnormal norm={norm:.4f}"
            )

        # 6. Validated cosine similarity matching
        try:
            sim_result = best_cosine_similarity(probe, templates)
            best_similarity = sim_result.best_similarity
            best_index = sim_result.matched_template_index
        except CosineSimilarityError as e:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=1, reason=f"SIMILARITY_ERROR: {e}"
            )

        # 7. Threshold decision
        if best_similarity >= config.FACE_MATCH_THRESHOLD:
            return FaceVerificationResult(
                verified=True, person_id=person_id,
                best_similarity=best_similarity,
                matched_template_index=best_index,
                faces_detected=1, reason="MATCH"
            )
        else:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=best_similarity,
                matched_template_index=best_index,
                faces_detected=1,
                reason=f"NO_MATCH (similarity {best_similarity:.4f} < threshold {config.FACE_MATCH_THRESHOLD:.2f})"
            )

    # ------------------------------------------------------------------
    # Multi-frame camera verification with majority vote
    # ------------------------------------------------------------------

    def verify_from_camera(
        self,
        person_id: str,
        camera_index: int = 0,
        timeout_seconds: float = 10.0,
        verbose: bool = False,
    ) -> FaceVerificationResult:
        """
        Opens a fresh camera session (buffer flushed on enter), captures frames and
        attempts face verification.

        Decision strategy:
        - Collects up to VERIFY_OBSERVATION_FRAMES accepted embeddings.
        - An accepted observation requires exactly one face, quality pass, and
          successful encoding. Frames that do NOT yield exactly one face are
          counted and reported but do NOT contribute to similarity.
        - Reports the MEDIAN similarity across accepted observations.
        - Declares MATCH only when median >= threshold.

        This prevents a single stale or accidental frame from causing a false match.
        """
        status = self.store.get_template_status(person_id)
        if status == TemplateStatus.NOT_ENROLLED:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="NO_ENROLLMENT"
            )
        if status in (TemplateStatus.LEGACY_TEMPLATE, TemplateStatus.RE_ENROLLMENT_REQUIRED):
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="RE_ENROLLMENT_REQUIRED"
            )
        if status == TemplateStatus.CORRUPTED_TEMPLATE:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="CORRUPTED_TEMPLATE"
            )

        OBSERVATION_TARGET = getattr(config, "VERIFY_OBSERVATION_FRAMES", 5)
        FRAME_SLEEP = 0.05  # 50 ms between frames

        print(f"[VERIFICATION] Starting verification stream for '{person_id}'...", flush=True)
        print(f"[VERIFICATION] Collecting up to {OBSERVATION_TARGET} accepted frames.", flush=True)

        start_time = time.time()
        frame_id = 0
        accepted_similarities: List[float] = []
        best_index_overall = -1
        no_face_frames = 0
        multi_face_frames = 0
        quality_reject_frames = 0

        try:
            with CameraManager(camera_index=camera_index) as camera:
                # CameraManager.__enter__ already calls flush_frames(5) — hardware buffer cleared
                while (
                    time.time() - start_time < timeout_seconds
                    and len(accepted_similarities) < OBSERVATION_TARGET
                ):
                    frame = camera.capture_frame()
                    frame_id += 1

                    res = self.verify_frame(
                        person_id, frame, frame_id=frame_id, verbose=verbose
                    )

                    if res.reason == "NO_FACE":
                        no_face_frames += 1
                        continue

                    if res.reason == "MULTIPLE_FACES":
                        multi_face_frames += 1
                        continue

                    if res.reason and res.reason.startswith("QUALITY_REJECT"):
                        quality_reject_frames += 1
                        continue

                    if res.reason and res.reason.startswith("ENCODE_FAIL"):
                        continue

                    if res.reason == "NO_ENROLLMENT":
                        return res  # Early exit — nothing to compare against

                    # Accepted observation — record similarity
                    accepted_similarities.append(res.best_similarity)
                    if res.matched_template_index >= 0:
                        best_index_overall = res.matched_template_index
                    print(
                        f"[VERIFICATION] Observation {len(accepted_similarities)}/{OBSERVATION_TARGET}: "
                        f"similarity={res.best_similarity:.4f}  frame_id={frame_id}",
                        flush=True
                    )

                    time.sleep(FRAME_SLEEP)

        except Exception as e:
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, error="Runtime error", reason=str(e)
            )

        # --- Aggregate results ---

        # No-face-only session
        if not accepted_similarities and no_face_frames > 0 and multi_face_frames == 0:
            print(f"[VERIFICATION] All {no_face_frames} frames had no face.", flush=True)
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason="Timeout: NO_FACE"
            )

        # Multiple-face-only session
        if not accepted_similarities and multi_face_frames > 0 and no_face_frames == 0:
            print(f"[VERIFICATION] All {multi_face_frames} frames had multiple faces.", flush=True)
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=multi_face_frames, reason="Timeout: MULTIPLE_FACES"
            )

        # Mixed or empty session with no accepted observations
        if not accepted_similarities:
            reason = (
                f"Timeout: no accepted frames "
                f"(no_face={no_face_frames} multi={multi_face_frames} quality_rej={quality_reject_frames})"
            )
            print(f"[VERIFICATION] {reason}", flush=True)
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=0.0, matched_template_index=-1,
                faces_detected=0, reason=reason
            )

        # Compute median similarity across accepted observations
        median_similarity = float(np.median(accepted_similarities))
        max_similarity = float(np.max(accepted_similarities))
        print(
            f"[VERIFICATION] Accepted observations: {len(accepted_similarities)}  "
            f"similarities={[round(s,4) for s in accepted_similarities]}  "
            f"median={median_similarity:.4f}  max={max_similarity:.4f}",
            flush=True
        )

        # Decision on MEDIAN (resistant to a single lucky/stale frame)
        if median_similarity >= config.FACE_MATCH_THRESHOLD:
            print(
                f"[VERIFICATION] MATCH: median similarity {median_similarity:.4f} >= "
                f"threshold {config.FACE_MATCH_THRESHOLD:.2f}", flush=True
            )
            return FaceVerificationResult(
                verified=True, person_id=person_id,
                best_similarity=median_similarity,
                matched_template_index=best_index_overall,
                faces_detected=len(accepted_similarities),
                reason="MATCH"
            )
        else:
            print(
                f"[VERIFICATION] NO MATCH: median similarity {median_similarity:.4f} < "
                f"threshold {config.FACE_MATCH_THRESHOLD:.2f}", flush=True
            )
            return FaceVerificationResult(
                verified=False, person_id=person_id,
                best_similarity=median_similarity,
                matched_template_index=best_index_overall,
                faces_detected=len(accepted_similarities),
                reason=f"NO_MATCH (median similarity {median_similarity:.4f} < threshold {config.FACE_MATCH_THRESHOLD:.2f})"
            )
