"""
Tests for InsightFaceRecognizer.

All tests mock the InsightFace FaceAnalysis so no real models/camera are needed.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from atlas_ui.backend.vision.face_recognizer import FaceEmbeddingResult
from atlas_ui.backend.vision.insightface_recognizer import InsightFaceRecognizer, EXPECTED_DIM


def _make_mock_app(face_embeddings=None, n_faces=1):
    """
    Build a mock InsightFace FaceAnalysis object.
    face_embeddings: list of per-face normed_embedding arrays; if None, uses random unit vecs.
    """
    mock_app = MagicMock()

    if n_faces == 0:
        mock_app.get.return_value = []
    else:
        faces = []
        for i in range(n_faces):
            face = MagicMock()
            face.bbox = [50.0, 50.0, 150.0, 150.0]  # centre at (100, 100)
            if face_embeddings and i < len(face_embeddings):
                emb = np.array(face_embeddings[i])
            else:
                v = np.random.randn(EXPECTED_DIM)
                emb = v / np.linalg.norm(v)
            face.normed_embedding = emb.astype(np.float32)
            faces.append(face)
        mock_app.get.return_value = faces

    return mock_app


def _make_recognizer(mock_app=None):
    """
    Build an InsightFaceRecognizer with mocked InsightFace internals.
    Resets the class-level singleton so each test gets a fresh instance.
    """
    # Reset class-level singleton
    InsightFaceRecognizer._app = None
    InsightFaceRecognizer._initialized = False

    if mock_app is None:
        mock_app = _make_mock_app()

    with patch("atlas_ui.backend.vision.insightface_recognizer.InsightFaceRecognizer._init_model"):
        rec = InsightFaceRecognizer.__new__(InsightFaceRecognizer)
        rec._providers = ["CPUExecutionProvider"]
        InsightFaceRecognizer._app = mock_app
        InsightFaceRecognizer._initialized = True

    return rec


VALID_FRAME = np.zeros((480, 640, 3), dtype=np.uint8)
VALID_BBOX = [50, 50, 150, 150]


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def test_insightface_empty_frame():
    """None or empty frame must return success=False."""
    rec = _make_recognizer()
    r1 = rec.encode(None, VALID_BBOX)
    assert r1.success is False
    assert "empty" in r1.error.lower()

    r2 = rec.encode(np.array([]), VALID_BBOX)
    assert r2.success is False
    assert "empty" in r2.error.lower()


def test_insightface_invalid_frame_shape():
    """2-D grayscale frames must be rejected."""
    rec = _make_recognizer()
    gray = np.zeros((480, 640), dtype=np.uint8)
    r = rec.encode(gray, VALID_BBOX)
    assert r.success is False
    assert "shape" in r.error.lower() or "channel" in r.error.lower()


def test_insightface_invalid_bbox():
    """Bounding box must have exactly 4 elements."""
    rec = _make_recognizer()
    r = rec.encode(VALID_FRAME, [10, 20])  # only 2 elements
    assert r.success is False
    assert "bbox" in r.error.lower()


def test_insightface_degenerate_bbox():
    """x1 >= x2 or y1 >= y2 must be rejected."""
    rec = _make_recognizer()
    r = rec.encode(VALID_FRAME, [100, 100, 50, 50])  # inverted
    assert r.success is False
    assert "degenerate" in r.error.lower() or "bbox" in r.error.lower()


def test_insightface_no_face_detected():
    """InsightFace detects 0 faces → encode failure."""
    rec = _make_recognizer(mock_app=_make_mock_app(n_faces=0))
    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is False
    assert "no faces" in r.error.lower()


# ---------------------------------------------------------------------------
# Successful embedding
# ---------------------------------------------------------------------------

def test_insightface_successful_embedding_dimension():
    """Successful encode must return 512-D embedding."""
    rec = _make_recognizer()
    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is True
    assert r.embedding_dimension == EXPECTED_DIM
    assert len(r.embedding) == EXPECTED_DIM


def test_insightface_finite_values():
    """All embedding values must be finite."""
    rec = _make_recognizer()
    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is True
    arr = np.array(r.embedding)
    assert np.isfinite(arr).all()


def test_insightface_l2_normalization():
    """Returned embedding must have L2 norm ≈ 1.0."""
    rec = _make_recognizer()
    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is True
    norm = float(np.linalg.norm(r.embedding))
    assert abs(norm - 1.0) < 0.01, f"L2 norm = {norm:.6f}, expected ~1.0"


def test_insightface_nan_in_embedding_rejected():
    """If InsightFace returns a NaN embedding, encode must fail."""
    nan_emb = np.full(EXPECTED_DIM, float("nan"), dtype=np.float32)
    mock_face = MagicMock()
    mock_face.bbox = [50.0, 50.0, 150.0, 150.0]
    mock_face.normed_embedding = nan_emb

    mock_app = MagicMock()
    mock_app.get.return_value = [mock_face]
    rec = _make_recognizer(mock_app=mock_app)

    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is False
    assert "nan" in r.error.lower() or "infinite" in r.error.lower()


def test_insightface_wrong_dimension_rejected():
    """If InsightFace returns a 128-D embedding instead of 512-D, encode must fail."""
    short_emb = np.random.randn(128).astype(np.float32)
    short_emb /= np.linalg.norm(short_emb)

    mock_face = MagicMock()
    mock_face.bbox = [50.0, 50.0, 150.0, 150.0]
    mock_face.normed_embedding = short_emb

    mock_app = MagicMock()
    mock_app.get.return_value = [mock_face]
    rec = _make_recognizer(mock_app=mock_app)

    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is False
    assert "512" in r.error


def test_insightface_bbox_match_tolerance():
    """Face far from YOLO bbox must be rejected (bbox match tolerance exceeded)."""
    mock_face = MagicMock()
    # InsightFace detects a face far from VALID_BBOX centre (100, 100)
    mock_face.bbox = [500.0, 400.0, 620.0, 480.0]  # centre at ~(560, 440) — 500px away
    v = np.random.randn(EXPECTED_DIM).astype(np.float32)
    mock_face.normed_embedding = v / np.linalg.norm(v)

    mock_app = MagicMock()
    mock_app.get.return_value = [mock_face]
    rec = _make_recognizer(mock_app=mock_app)

    r = rec.encode(VALID_FRAME, VALID_BBOX)
    assert r.success is False
    assert "tolerance" in r.error.lower() or "distance" in r.error.lower() or "px" in r.error.lower()
