"""
Tests for FaceVerificationService with InsightFace recognizer interface.

encode() now takes (frame, bbox). Mocks updated accordingly.
Template store now uses get_template_status() instead of has_templates().
"""
import pytest
import numpy as np
from unittest.mock import MagicMock

from atlas_ui.backend.vision.face_verification_service import FaceVerificationService, FaceVerificationResult
from atlas_ui.backend.vision.face_detection_result import FaceDetection, FaceDetectionResult
from atlas_ui.backend.vision.face_recognizer import FaceEmbeddingResult
from atlas_ui.backend.vision.face_template_store import TemplateStatus
from atlas_ui.backend.vision import config


def create_sharp_frame():
    """Checkerboard frame that passes face quality checks."""
    sharp_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(100):
        for j in range(100):
            if (i // 5 + j // 5) % 2 == 0:
                sharp_crop[i, j] = [120, 120, 120]
            else:
                sharp_crop[i, j] = [60, 60, 60]
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[50:150, 50:150] = sharp_crop
    return frame


def _mock_store(status: TemplateStatus, templates=None):
    """Build a mock FaceTemplateStore with the given template status."""
    mock_store = MagicMock()
    mock_store.get_template_status.return_value = status
    mock_store.has_templates.return_value = (status != TemplateStatus.NOT_ENROLLED)
    mock_store.get_templates.return_value = templates or []
    return mock_store


def test_face_verification_no_face():
    """No face detected → NO_FACE result, encode not called."""
    mock_detector = MagicMock()
    mock_detector.detect.return_value = FaceDetectionResult(faces=[], face_count=0)

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[0.1, 0.2, 0.3]])
    mock_recognizer = MagicMock()

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert res.reason == "NO_FACE"


def test_face_verification_multiple_faces():
    """Multiple faces → MULTIPLE_FACES, encode not called."""
    mock_detector = MagicMock()
    face1 = FaceDetection(bbox=[10, 10, 90, 90], confidence=0.9)
    face2 = FaceDetection(bbox=[100, 100, 180, 180], confidence=0.8)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face1, face2], face_count=2)

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[0.1, 0.2, 0.3]])
    mock_recognizer = MagicMock()

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert res.reason == "MULTIPLE_FACES"
    assert res.faces_detected == 2


def test_face_verification_no_enrollment():
    """No templates at all → NO_ENROLLMENT."""
    mock_detector = MagicMock()
    mock_recognizer = MagicMock()
    mock_store = _mock_store(TemplateStatus.NOT_ENROLLED)

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert res.reason == "NO_ENROLLMENT"


def test_face_verification_legacy_template_requires_reenrollment():
    """LEGACY_TEMPLATE status → RE_ENROLLMENT_REQUIRED, no encode."""
    mock_detector = MagicMock()
    mock_recognizer = MagicMock()
    mock_store = _mock_store(TemplateStatus.LEGACY_TEMPLATE, [[0.1, 0.2]])

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert res.reason == "RE_ENROLLMENT_REQUIRED"
    mock_recognizer.encode.assert_not_called()


def test_face_verification_recognizer_mismatch_requires_reenrollment():
    """RE_ENROLLMENT_REQUIRED status → returns that reason, no encode."""
    mock_detector = MagicMock()
    mock_recognizer = MagicMock()
    mock_store = _mock_store(TemplateStatus.RE_ENROLLMENT_REQUIRED, [[0.1, 0.2]])

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert res.reason == "RE_ENROLLMENT_REQUIRED"
    mock_recognizer.encode.assert_not_called()


def test_face_verification_match_success():
    """Enrolled person with matching embedding → verified=True, MATCH."""
    mock_detector = MagicMock()
    face = FaceDetection(bbox=[50, 50, 150, 150], confidence=0.95)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face], face_count=1)

    mock_recognizer = MagicMock()
    mock_recognizer.encode.return_value = FaceEmbeddingResult(
        success=True, embedding=[1.0, 0.0], embedding_dimension=2
    )

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[1.0, 0.0]])

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = create_sharp_frame()

    res = service.verify_frame("user-1", frame)
    assert res.verified is True
    assert res.reason == "MATCH"
    assert pytest.approx(res.best_similarity) == 1.0


def test_face_verification_below_threshold():
    """Orthogonal vectors → similarity=0.0 → NO_MATCH."""
    mock_detector = MagicMock()
    face = FaceDetection(bbox=[50, 50, 150, 150], confidence=0.95)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face], face_count=1)

    mock_recognizer = MagicMock()
    mock_recognizer.encode.return_value = FaceEmbeddingResult(
        success=True, embedding=[1.0, 0.0], embedding_dimension=2
    )

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[0.0, 1.0]])  # orthogonal

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = create_sharp_frame()

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert "NO_MATCH" in res.reason
    assert pytest.approx(res.best_similarity) == 0.0


def test_face_verification_no_face_does_not_call_encode():
    """NO_FACE must not call encode()."""
    mock_detector = MagicMock()
    mock_detector.detect.return_value = FaceDetectionResult(faces=[], face_count=0)

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[0.1, 0.2]])
    mock_recognizer = MagicMock()

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    res = service.verify_frame("user-1", np.zeros((300, 300, 3), dtype=np.uint8))

    assert res.verified is False
    assert res.reason == "NO_FACE"
    mock_recognizer.encode.assert_not_called()


def test_face_verification_multiple_faces_does_not_call_encode():
    """MULTIPLE_FACES must not call encode()."""
    mock_detector = MagicMock()
    face1 = FaceDetection(bbox=[10, 10, 90, 90], confidence=0.9)
    face2 = FaceDetection(bbox=[110, 10, 190, 90], confidence=0.85)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face1, face2], face_count=2)

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[0.1, 0.2]])
    mock_recognizer = MagicMock()

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    res = service.verify_frame("user-1", np.zeros((300, 300, 3), dtype=np.uint8))

    assert res.verified is False
    assert res.reason == "MULTIPLE_FACES"
    mock_recognizer.encode.assert_not_called()


def test_face_verification_encode_failure_returns_false():
    """A failed encode must return verified=False, not raise."""
    mock_detector = MagicMock()
    face = FaceDetection(bbox=[50, 50, 150, 150], confidence=0.95)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face], face_count=1)

    mock_recognizer = MagicMock()
    mock_recognizer.encode.return_value = FaceEmbeddingResult(
        success=False, error="InsightFace inference failed"
    )

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[1.0, 0.0]])

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = create_sharp_frame()

    res = service.verify_frame("user-1", frame)
    assert res.verified is False
    assert "ENCODE_FAIL" in res.reason


def test_face_verification_encode_called_with_frame_and_bbox():
    """encode() must be called with (frame, bbox) — not (crop,)."""
    mock_detector = MagicMock()
    face = FaceDetection(bbox=[50, 50, 150, 150], confidence=0.95)
    mock_detector.detect.return_value = FaceDetectionResult(faces=[face], face_count=1)

    mock_recognizer = MagicMock()
    mock_recognizer.encode.return_value = FaceEmbeddingResult(
        success=True, embedding=[1.0, 0.0], embedding_dimension=2
    )

    mock_store = _mock_store(TemplateStatus.ENROLLED, [[1.0, 0.0]])

    service = FaceVerificationService(mock_detector, mock_recognizer, mock_store)
    frame = create_sharp_frame()

    service.verify_frame("user-1", frame)

    # encode must have been called with positional args: (frame, bbox)
    mock_recognizer.encode.assert_called_once()
    call_args = mock_recognizer.encode.call_args[0]  # positional args
    assert len(call_args) == 2, "encode() must be called with (frame, bbox)"
    assert isinstance(call_args[0], np.ndarray), "First arg must be frame (ndarray)"
    assert isinstance(call_args[1], list), "Second arg must be bbox (list)"
    assert call_args[1] == [50, 50, 150, 150]
