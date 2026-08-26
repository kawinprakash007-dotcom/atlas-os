"""
InsightFace buffalo_l Face Recognizer

Production ArcFace implementation using InsightFace buffalo_l model pack.
Provides proper 5-point face alignment via InsightFace's internal landmark detector,
then generates a 512-D L2-normalized ArcFace embedding.

Architecture:
    Full BGR frame + YOLO bbox
        ↓
    InsightFace FaceAnalysis.get(frame)   — runs detection + landmarks + alignment + embedding
        ↓
    Match detected face closest to YOLO bbox
        ↓
    face.normed_embedding  — 512-D L2-normalized ArcFace vector
        ↓
    FaceEmbeddingResult

Design decisions:
    - InsightFace's internal detector runs on the FULL frame for reliable landmark detection.
      YOLO bounding boxes are used as a guide to SELECT which detected face to use when
      InsightFace detects multiple.
    - 5-point facial landmark alignment is performed internally by InsightFace's
      ArcFace pipeline. This is NOT available when feeding only a crop.
    - Model is initialized ONCE at construction; not re-initialized per encode() call.
    - CPUExecutionProvider used by default.
"""

import os
import numpy as np
from typing import List, Optional

from atlas_ui.backend.vision.face_recognizer import FaceRecognizer, FaceEmbeddingResult

# Recognizer identifier persisted in template metadata
RECOGNIZER_ID = "insightface_buffalo_l"

# Expected embedding dimension from buffalo_l ArcFace ResNet50
EXPECTED_DIM = 512

# Max pixel distance between YOLO bbox centre and InsightFace bbox centre
# to consider them the same face.
BBOX_MATCH_TOLERANCE_PX = 80


class InsightFaceRecognizer(FaceRecognizer):
    """
    ONNX-backed ArcFace embedding generator using InsightFace buffalo_l.

    Requires InsightFace to be installed:
        pip install insightface

    Model pack is automatically downloaded to ~/.insightface/models/buffalo_l/
    on first use. Subsequent uses load from disk (no network required).
    """

    _app = None          # class-level singleton to avoid repeated model loads
    _initialized = False

    def __init__(self, providers: Optional[List[str]] = None):
        self._providers = providers or ["CPUExecutionProvider"]
        self._init_model()

    def _init_model(self) -> None:
        """
        Initialize InsightFace FaceAnalysis with buffalo_l model pack.
        Downloads model weights on first call; subsequent calls load from cache.
        Initialization is expensive (~2-5 seconds on CPU) so we cache the app
        at the class level.
        """
        if InsightFaceRecognizer._initialized:
            print("[INSIGHTFACE] Model already initialized (reusing class-level instance).", flush=True)
            return

        print("[INSIGHTFACE] Initializing buffalo_l model pack...", flush=True)
        try:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(name="buffalo_l", providers=self._providers)
            app.prepare(ctx_id=-1, det_size=(640, 640))

            InsightFaceRecognizer._app = app
            InsightFaceRecognizer._initialized = True

            # Print startup diagnostic (once only)
            print("[INSIGHTFACE DIAGNOSTIC] ========================", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Model pack    : buffalo_l", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Recognizer    : ArcFace ResNet50 (w600k_r50.onnx)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Det model     : RetinaFace (det_10g.onnx)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Alignment     : ENABLED (5-point landmark alignment)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Input size    : 112x112 (post-alignment)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Color order   : BGR (InsightFace handles BGR natively)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Normalization : (pixel - 127.5) / 128.0 (internal)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Embedding dim : {EXPECTED_DIM} (L2-normalized)", flush=True)
            print(f"[INSIGHTFACE DIAGNOSTIC] Providers     : {self._providers}", flush=True)
            print("[INSIGHTFACE DIAGNOSTIC] ========================", flush=True)

        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize InsightFace buffalo_l: {e}\n"
                f"Ensure 'insightface' is installed: pip install insightface"
            )

    @property
    def app(self):
        if InsightFaceRecognizer._app is None:
            raise RuntimeError("InsightFaceRecognizer not initialized properly.")
        return InsightFaceRecognizer._app

    def encode(self, frame: np.ndarray, bbox: List[int]) -> FaceEmbeddingResult:
        """
        Generate a 512-D L2-normalized face embedding for the face indicated
        by `bbox` within `frame`.

        Args:
            frame: Full BGR camera frame (H x W x 3, uint8).
            bbox:  [x1, y1, x2, y2] YOLO bounding box (integer pixel coords).

        Returns:
            FaceEmbeddingResult with:
                success=True  → embedding is 512-D, finite, L2-norm ≈ 1.0
                success=False → error describes the failure reason

        Strategy:
            1. Validate inputs.
            2. Run InsightFace FaceAnalysis on the full frame.
               InsightFace internally: detects faces → finds landmarks →
               warps to aligned 112x112 → runs ArcFace ResNet50.
            3. Select the detected face whose centre is closest to the YOLO bbox centre.
               If no InsightFace face is within BBOX_MATCH_TOLERANCE_PX of the YOLO
               centre, return ENCODE_FAIL.
            4. Validate and return face.normed_embedding.
        """
        # --- 1. Input validation ---
        if frame is None or frame.size == 0:
            return FaceEmbeddingResult(success=False, error="Input frame is empty.")

        if frame.ndim != 3 or frame.shape[2] != 3:
            return FaceEmbeddingResult(
                success=False,
                error=f"Invalid frame shape: {frame.shape}. Expected (H, W, 3)."
            )

        if not np.isfinite(frame.astype(np.float32)).all():
            return FaceEmbeddingResult(success=False, error="Frame contains NaN or infinite pixel values.")

        if len(bbox) != 4:
            return FaceEmbeddingResult(
                success=False,
                error=f"Invalid bbox: expected [x1, y1, x2, y2], got length {len(bbox)}."
            )

        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        if x1 >= x2 or y1 >= y2:
            return FaceEmbeddingResult(
                success=False,
                error=f"Degenerate bbox: {bbox}."
            )

        yolo_cx = (x1 + x2) / 2.0
        yolo_cy = (y1 + y2) / 2.0

        # --- 2. InsightFace inference on full frame ---
        try:
            faces = self.app.get(frame)
        except Exception as e:
            return FaceEmbeddingResult(success=False, error=f"InsightFace inference error: {e}")

        if not faces:
            return FaceEmbeddingResult(
                success=False,
                error="InsightFace detected no faces in frame (YOLO had 1). "
                      "Possible cause: face too small, poor lighting, or extreme angle."
            )

        # --- 3. Select the face closest to YOLO bbox centre ---
        best_face = None
        best_dist = float("inf")

        for face in faces:
            fb = face.bbox  # [x1, y1, x2, y2] from InsightFace
            fx_cx = (fb[0] + fb[2]) / 2.0
            fx_cy = (fb[1] + fb[3]) / 2.0
            dist = ((fx_cx - yolo_cx) ** 2 + (fx_cy - yolo_cy) ** 2) ** 0.5

            if dist < best_dist:
                best_dist = dist
                best_face = face

        if best_dist > BBOX_MATCH_TOLERANCE_PX:
            return FaceEmbeddingResult(
                success=False,
                error=(
                    f"InsightFace nearest face centre is {best_dist:.1f}px from YOLO bbox centre "
                    f"(tolerance: {BBOX_MATCH_TOLERANCE_PX}px). Faces may not correspond."
                )
            )

        # --- 4. Extract and validate embedding ---
        if best_face.normed_embedding is None:
            return FaceEmbeddingResult(
                success=False,
                error="InsightFace returned a face with no embedding (recognition model may have failed)."
            )

        embedding = np.array(best_face.normed_embedding, dtype=np.float64)

        if embedding.ndim != 1 or len(embedding) != EXPECTED_DIM:
            return FaceEmbeddingResult(
                success=False,
                error=f"Unexpected embedding shape: {embedding.shape}. Expected ({EXPECTED_DIM},)."
            )

        if not np.isfinite(embedding).all():
            return FaceEmbeddingResult(
                success=False,
                error="InsightFace embedding contains NaN or infinite values."
            )

        norm = float(np.linalg.norm(embedding))
        if abs(norm - 1.0) > 0.05:
            # normed_embedding should already be unit norm; re-normalize defensively
            if norm < 1e-6:
                return FaceEmbeddingResult(
                    success=False,
                    error=f"Embedding has near-zero L2 norm: {norm:.6f}."
                )
            embedding = embedding / norm

        return FaceEmbeddingResult(
            success=True,
            embedding=embedding.tolist(),
            embedding_dimension=EXPECTED_DIM,
        )
