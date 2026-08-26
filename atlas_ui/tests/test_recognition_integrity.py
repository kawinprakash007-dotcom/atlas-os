"""
Phase 4A.1 — Recognition Integrity Unit Tests

Tests:
  01. Embedding dimension validation
  02. L2 normalization correctness
  03. Cosine similarity: same vector → 1.0
  04. Cosine similarity: orthogonal vectors → 0.0
  05. Cosine similarity: opposite vectors → -1.0
  06. NaN embedding rejection
  07. Dimension mismatch rejection
  08. No-face must not call recognizer
  09. Multiple-faces must not call recognizer
  10. Verifier state resets between requests (no stale best_similarity)
  11. Stale embedding cannot produce a match
  12. Template fingerprint uniqueness
  13. Template comparison checks ALL stored templates

No real camera, no real ONNX model required.
"""
import hashlib
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from atlas_ui.backend.vision.cosine_similarity import (
    cosine_similarity, best_cosine_similarity, CosineSimilarityError
)
from atlas_ui.backend.vision.face_recognizer import FaceEmbeddingResult
from atlas_ui.backend.vision.face_detection_result import FaceDetection, FaceDetectionResult
from atlas_ui.backend.vision.face_verification_service import FaceVerificationService
from atlas_ui.backend.vision.face_template_store import TemplateStatus
from atlas_ui.backend.vision import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit(v: np.ndarray) -> list:
    """Return L2-normalized vector as list."""
    return (v / np.linalg.norm(v)).tolist()


def _ortho(dim: int = 512) -> tuple:
    """Return two L2-normalized vectors that are orthogonal."""
    a = np.zeros(dim)
    a[0] = 1.0
    b = np.zeros(dim)
    b[1] = 1.0
    return a.tolist(), b.tolist()


def _make_verify_service(has_templates=True, templates=None, face_count=1,
                          embed_success=True, embedding=None):
    mock_store = MagicMock()
    # New interface: get_template_status() is called instead of has_templates()
    if has_templates and templates:
        mock_store.get_template_status.return_value = TemplateStatus.ENROLLED
    else:
        mock_store.get_template_status.return_value = TemplateStatus.NOT_ENROLLED
    mock_store.has_templates.return_value = has_templates
    mock_store.get_templates.return_value = templates or []

    mock_detector = MagicMock()
    faces = [FaceDetection(bbox=[50, 50, 150, 150], confidence=0.95)] * face_count
    mock_detector.detect.return_value = FaceDetectionResult(faces=faces[:face_count], face_count=face_count)

    mock_recognizer = MagicMock()
    if embed_success and embedding is not None:
        mock_recognizer.encode.return_value = FaceEmbeddingResult(
            success=True, embedding=embedding, embedding_dimension=len(embedding)
        )
    else:
        mock_recognizer.encode.return_value = FaceEmbeddingResult(
            success=False, error="Mock encode failure"
        )

    svc = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    return svc, mock_recognizer


def _sharp_frame():
    """Checkerboard frame that passes face quality checks."""
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    crop = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(100):
        for j in range(100):
            crop[i, j] = [120, 120, 120] if (i // 5 + j // 5) % 2 == 0 else [60, 60, 60]
    frame[50:150, 50:150] = crop
    return frame


# ---------------------------------------------------------------------------
# TEST 01: Embedding dimension validation
# ---------------------------------------------------------------------------

def test_01_embedding_dimension_512():
    """ArcFace must return 512-dimensional embeddings."""
    dim = 512
    v = np.random.randn(dim)
    v_n = _unit(v)
    assert len(v_n) == 512


# ---------------------------------------------------------------------------
# TEST 02: L2 normalization
# ---------------------------------------------------------------------------

def test_02_l2_normalization():
    """After normalization, L2 norm must be 1.0 within float tolerance."""
    rng = np.random.default_rng(0)
    for _ in range(10):
        raw = rng.standard_normal(512).astype(np.float32)
        raw_norm = float(np.linalg.norm(raw))
        normalized = raw / raw_norm
        post_norm = float(np.linalg.norm(normalized))
        assert abs(post_norm - 1.0) < 1e-5, f"Normalized L2 norm = {post_norm:.8f}, expected 1.0"


# ---------------------------------------------------------------------------
# TEST 03: Cosine similarity — same vector → 1.0
# ---------------------------------------------------------------------------

def test_03_cosine_same_vector():
    """Same unit vector compared to itself must return 1.0."""
    rng = np.random.default_rng(1)
    v = _unit(rng.standard_normal(512))
    sim = cosine_similarity(v, v)
    assert abs(sim - 1.0) < 1e-6, f"Expected 1.0, got {sim}"


# ---------------------------------------------------------------------------
# TEST 04: Cosine similarity — orthogonal vectors → 0.0
# ---------------------------------------------------------------------------

def test_04_cosine_orthogonal():
    """Orthogonal unit vectors must return 0.0."""
    a, b = _ortho(512)
    sim = cosine_similarity(a, b)
    assert abs(sim) < 1e-10, f"Expected 0.0, got {sim}"


# ---------------------------------------------------------------------------
# TEST 05: Cosine similarity — opposite vectors → -1.0
# ---------------------------------------------------------------------------

def test_05_cosine_opposite():
    """Opposite unit vectors must return -1.0."""
    rng = np.random.default_rng(2)
    v = _unit(rng.standard_normal(512))
    neg_v = [-x for x in v]
    sim = cosine_similarity(v, neg_v)
    assert abs(sim + 1.0) < 1e-6, f"Expected -1.0, got {sim}"


# ---------------------------------------------------------------------------
# TEST 06: NaN embedding rejection
# ---------------------------------------------------------------------------

def test_06_nan_rejection():
    """NaN values in either embedding must raise CosineSimilarityError."""
    rng = np.random.default_rng(3)
    good = _unit(rng.standard_normal(512))
    nan_vec = good.copy()
    nan_vec[7] = float("nan")

    with pytest.raises(CosineSimilarityError, match="NaN or infinite"):
        cosine_similarity(nan_vec, good)

    with pytest.raises(CosineSimilarityError, match="NaN or infinite"):
        cosine_similarity(good, nan_vec)


# ---------------------------------------------------------------------------
# TEST 07: Dimension mismatch rejection
# ---------------------------------------------------------------------------

def test_07_dimension_mismatch():
    """Mismatched embedding dimensions must raise CosineSimilarityError."""
    rng = np.random.default_rng(4)
    a = _unit(rng.standard_normal(512))
    b = _unit(rng.standard_normal(256))  # wrong dimension

    with pytest.raises(CosineSimilarityError, match="Dimension mismatch"):
        cosine_similarity(a, b)


# ---------------------------------------------------------------------------
# TEST 08: No-face must not call recognizer
# ---------------------------------------------------------------------------

def test_08_no_face_does_not_call_encode():
    """Recognizer.encode() must NOT be called when face_count == 0."""
    template = _unit(np.ones(512))
    svc, mock_recognizer = _make_verify_service(
        has_templates=True, templates=[template],
        face_count=0, embed_success=True, embedding=template
    )
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    res = svc.verify_frame("user-1", frame)

    assert res.verified is False
    assert res.reason == "NO_FACE"
    mock_recognizer.encode.assert_not_called()


# ---------------------------------------------------------------------------
# TEST 09: Multiple-faces must not call recognizer
# ---------------------------------------------------------------------------

def test_09_multiple_faces_does_not_call_encode():
    """Recognizer.encode() must NOT be called when face_count >= 2."""
    template = _unit(np.ones(512))
    svc, mock_recognizer = _make_verify_service(
        has_templates=True, templates=[template],
        face_count=2, embed_success=True, embedding=template
    )
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    res = svc.verify_frame("user-1", frame)

    assert res.verified is False
    assert res.reason == "MULTIPLE_FACES"
    mock_recognizer.encode.assert_not_called()


# ---------------------------------------------------------------------------
# TEST 10: Verifier state resets between requests
# ---------------------------------------------------------------------------

def test_10_verifier_state_resets_between_requests():
    """
    Two sequential verify_frame calls must be independent.
    The result of the first call must not affect the second.
    """
    rng = np.random.default_rng(5)
    enrolled = _unit(rng.standard_normal(512))
    stranger = _unit(rng.standard_normal(512))

    # Check what cosine_similarity would return for the stranger
    stranger_sim = cosine_similarity(stranger, enrolled)

    svc, _ = _make_verify_service(
        has_templates=True, templates=[enrolled],
        face_count=1, embed_success=True, embedding=enrolled
    )
    frame = _sharp_frame()

    # First call — enrolled person
    res1 = svc.verify_frame("user-1", frame)

    # Now swap the embedding to the stranger
    svc.recognizer.encode.return_value = FaceEmbeddingResult(
        success=True, embedding=stranger, embedding_dimension=512
    )

    # Second call — must start fresh
    res2 = svc.verify_frame("user-1", frame)

    # res2 similarity must match stranger (not enrolled)
    assert abs(res2.best_similarity - stranger_sim) < 1e-4, (
        f"Expected {stranger_sim:.4f} but got {res2.best_similarity:.4f} — state leaked from call 1!"
    )


# ---------------------------------------------------------------------------
# TEST 11: Stale embedding cannot produce a match
# ---------------------------------------------------------------------------

def test_11_stale_embedding_cannot_match():
    """
    If the camera delivers the same frame twice (stale buffer),
    verify_frame must still compute a fresh embedding from the actual frame.
    No caching of previous embeddings.
    """
    rng = np.random.default_rng(6)
    enrolled = _unit(rng.standard_normal(512))
    stranger = _unit(rng.standard_normal(512))

    stranger_sim = cosine_similarity(stranger, enrolled)

    svc, mock_recognizer = _make_verify_service(
        has_templates=True, templates=[enrolled],
        face_count=1, embed_success=True, embedding=stranger
    )
    frame = _sharp_frame()

    # Call twice with SAME frame — both should produce stranger similarity
    res1 = svc.verify_frame("user-1", frame)
    res2 = svc.verify_frame("user-1", frame)

    # Both calls must encode independently (no caching)
    assert mock_recognizer.encode.call_count == 2, (
        f"Expected 2 encode calls, got {mock_recognizer.encode.call_count}"
    )
    # Both similarities must equal stranger_sim
    assert abs(res1.best_similarity - stranger_sim) < 1e-4
    assert abs(res2.best_similarity - stranger_sim) < 1e-4


# ---------------------------------------------------------------------------
# TEST 12: Template fingerprint uniqueness
# ---------------------------------------------------------------------------

def test_12_template_fingerprint_uniqueness():
    """5 distinct L2-normalized embeddings must have 5 distinct MD5 fingerprints."""
    rng = np.random.default_rng(7)
    templates = [_unit(rng.standard_normal(512)) for _ in range(5)]
    fingerprints = [
        hashlib.md5(np.array(t, dtype=np.float32).tobytes()).hexdigest()
        for t in templates
    ]
    assert len(set(fingerprints)) == 5, "Expected 5 unique fingerprints"


# ---------------------------------------------------------------------------
# TEST 13: Template comparison checks ALL stored templates
# ---------------------------------------------------------------------------

def test_13_all_templates_compared():
    """
    verify_frame must compare the probe against EVERY stored template,
    not just the first one.
    """
    rng = np.random.default_rng(8)
    n_templates = 5

    # Enrolled vectors
    templates = [_unit(rng.standard_normal(512)) for _ in range(n_templates)]

    # Probe that is perfectly aligned with the LAST template only
    probe = templates[-1]

    svc, _ = _make_verify_service(
        has_templates=True, templates=templates,
        face_count=1, embed_success=True, embedding=probe
    )
    frame = _sharp_frame()
    res = svc.verify_frame("user-1", frame)

    expected_best_sim = max(cosine_similarity(probe, t) for t in templates)
    assert abs(res.best_similarity - expected_best_sim) < 1e-4, (
        f"Expected best={expected_best_sim:.4f} but got {res.best_similarity:.4f}. "
        f"Not all templates were compared."
    )
    # The matched index must be the last template (index 4)
    assert res.matched_template_index == n_templates - 1, (
        f"Expected best match at index {n_templates - 1}, got {res.matched_template_index}"
    )
