"""
Tests for the FaceRecognizer abstract interface and FaceEmbeddingResult.

ArcFaceRecognizer has been retired (garavv/arcface-onnx model). These tests
now verify the contract using a minimal ConcreteRecognizer stub and cover
the FaceEmbeddingResult dataclass.
"""
import numpy as np
import pytest

from atlas_ui.backend.vision.face_recognizer import FaceRecognizer, FaceEmbeddingResult


class ConcreteRecognizer(FaceRecognizer):
    """Minimal concrete implementation to test the abstract interface contract."""

    def __init__(self, fixed_embedding=None):
        self._fixed = fixed_embedding

    def encode(self, frame: np.ndarray, bbox) -> FaceEmbeddingResult:
        if frame is None or frame.size == 0:
            return FaceEmbeddingResult(success=False, error="empty input")

        if frame.ndim != 3 or frame.shape[2] != 3:
            return FaceEmbeddingResult(success=False, error="invalid ndim or channels")

        if frame.shape[0] < 10 or frame.shape[1] < 10:
            return FaceEmbeddingResult(success=False, error="invalid dimensions (too small)")

        emb = self._fixed if self._fixed is not None else np.random.randn(512)
        arr = np.array(emb, dtype=np.float64)

        if not np.isfinite(arr).all():
            return FaceEmbeddingResult(success=False, error="NaN or infinite values in output")

        norm = float(np.linalg.norm(arr))
        if norm < 1e-6:
            return FaceEmbeddingResult(success=False, error="near-zero L2 norm")
        arr = arr / norm

        return FaceEmbeddingResult(success=True, embedding=arr.tolist(), embedding_dimension=len(arr))


# ---------------------------------------------------------------------------
# FaceEmbeddingResult contract
# ---------------------------------------------------------------------------

def test_embedding_result_success_fields():
    res = FaceEmbeddingResult(success=True, embedding=[1.0, 0.0], embedding_dimension=2)
    assert res.success is True
    assert res.embedding == [1.0, 0.0]
    assert res.embedding_dimension == 2
    assert res.error is None


def test_embedding_result_failure_fields():
    res = FaceEmbeddingResult(success=False, error="model error")
    assert res.success is False
    assert res.error == "model error"
    assert res.embedding is None
    assert res.embedding_dimension == 0


# ---------------------------------------------------------------------------
# Abstract interface (via ConcreteRecognizer)
# ---------------------------------------------------------------------------

def test_concrete_recognizer_empty_input():
    rec = ConcreteRecognizer()
    res = rec.encode(None, [0, 0, 100, 100])
    assert res.success is False
    assert "empty" in res.error

    res2 = rec.encode(np.array([]), [0, 0, 100, 100])
    assert res2.success is False
    assert "empty" in res2.error


def test_concrete_recognizer_invalid_ndim():
    rec = ConcreteRecognizer()
    img_2d = np.zeros((112, 112), dtype=np.uint8)
    res = rec.encode(img_2d, [0, 0, 100, 100])
    assert res.success is False
    assert "ndim" in res.error or "channel" in res.error


def test_concrete_recognizer_too_small():
    rec = ConcreteRecognizer()
    img_small = np.zeros((5, 5, 3), dtype=np.uint8)
    res = rec.encode(img_small, [0, 0, 5, 5])
    assert res.success is False
    assert "dimensions" in res.error


def test_concrete_recognizer_embedding_normalization():
    """encode() must return an L2-normalized embedding."""
    raw = np.array([3.0, 4.0])  # L2 norm = 5.0, normalized → [0.6, 0.8]
    rec = ConcreteRecognizer(fixed_embedding=raw)
    img = np.zeros((112, 112, 3), dtype=np.uint8)

    res = rec.encode(img, [0, 0, 100, 100])
    assert res.success is True
    assert res.embedding_dimension == 2
    assert pytest.approx(res.embedding[0]) == 0.6
    assert pytest.approx(res.embedding[1]) == 0.8
    norm = float(np.linalg.norm(res.embedding))
    assert pytest.approx(norm) == 1.0


def test_concrete_recognizer_nan_rejection():
    """NaN values in model output must cause success=False."""
    nan_emb = [float("nan"), 1.0]
    rec = ConcreteRecognizer(fixed_embedding=nan_emb)
    img = np.zeros((112, 112, 3), dtype=np.uint8)

    res = rec.encode(img, [0, 0, 100, 100])
    assert res.success is False
    assert "NaN or infinite" in res.error


def test_concrete_recognizer_inf_rejection():
    """Inf values in model output must cause success=False."""
    inf_emb = [float("inf"), 1.0]
    rec = ConcreteRecognizer(fixed_embedding=inf_emb)
    img = np.zeros((112, 112, 3), dtype=np.uint8)

    res = rec.encode(img, [0, 0, 100, 100])
    assert res.success is False
    assert "NaN or infinite" in res.error


def test_concrete_recognizer_zero_norm_rejection():
    """Zero-norm output must cause success=False."""
    rec = ConcreteRecognizer(fixed_embedding=[0.0, 0.0])
    img = np.zeros((112, 112, 3), dtype=np.uint8)

    res = rec.encode(img, [0, 0, 100, 100])
    assert res.success is False
    assert "near-zero L2 norm" in res.error


def test_interface_encode_signature_requires_frame_and_bbox():
    """encode() must accept (frame: ndarray, bbox: list) — not a crop alone."""
    import inspect
    sig = inspect.signature(FaceRecognizer.encode)
    params = list(sig.parameters.keys())
    assert "frame" in params, "encode() must have a 'frame' parameter"
    assert "bbox" in params, "encode() must have a 'bbox' parameter"
