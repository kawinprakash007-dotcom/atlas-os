"""
Phase 4A — Biometric API Tests

All 18 required test cases. No real camera, no real ONNX model.
Uses FastAPI TestClient and unittest.mock to inject controlled behaviour
into FaceTemplateStore, FaceEnrollmentService, and FaceVerificationService.

Test IDs:
    STATUS:
        01 — person enrolled
        02 — person not enrolled
        03 — person not in registry (404)

    ENROLL:
        04 — successful enrollment
        05 — person not in registry (404)
        06 — already enrolled (409)
        07 — camera unavailable (503)
        08 — insufficient samples (422)
        09 — persistence failure (500)
        10 — camera busy (409)

    VERIFY:
        11 — successful match (200, verified=True)
        12 — failed match (200, verified=False)
        13 — no biometric enrollment (400)
        14 — person not in registry (404)
        15 — no face (200, verified=False, reason=NO_FACE)
        16 — multiple faces (200, verified=False, reason=MULTIPLE_FACES)
        17 — camera unavailable (503)
        18 — camera busy (409)
"""

import threading
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from fastapi.testclient import TestClient

from atlas_ui.backend.main import app
from atlas_ui.backend.vision.face_enrollment_service import FaceEnrollmentResult
from atlas_ui.backend.vision.face_verification_service import FaceVerificationResult
import atlas_ui.backend.routes.biometric as biometric_route_module
from atlas_ui.backend.vision.face_template_store import TemplateStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)

ENROLLED_PERSON_ID = "ATLAS-P-88888888"   # seeded by main.py
UNKNOWN_PERSON_ID = "ATLAS-P-99999999"


def _fake_templates(n: int = 5, dim: int = 512):
    """Returns n fake L2-normalized embeddings of `dim` dimensions."""
    import numpy as np
    templates = []
    for _ in range(n):
        v = np.random.randn(dim).astype(float)
        v /= float(np.linalg.norm(v))
        templates.append(v.tolist())
    return templates


def _enroll_ok_result(n: int = 5) -> FaceEnrollmentResult:
    return FaceEnrollmentResult(
        success=True,
        person_id=ENROLLED_PERSON_ID,
        samples_requested=5,
        samples_captured=n,
        samples_rejected=0,
        reason="ENROLLMENT_COMPLETED",
    )


def _enroll_fail_result(reason: str, captured: int = 0) -> FaceEnrollmentResult:
    return FaceEnrollmentResult(
        success=False,
        person_id=ENROLLED_PERSON_ID,
        samples_requested=5,
        samples_captured=captured,
        samples_rejected=0,
        reason=reason,
        error=reason,
    )


def _verify_match_result(similarity: float = 0.85) -> FaceVerificationResult:
    return FaceVerificationResult(
        verified=True,
        person_id=ENROLLED_PERSON_ID,
        best_similarity=similarity,
        matched_template_index=0,
        faces_detected=1,
        reason="MATCH",
    )


def _verify_fail_result(reason: str, similarity: float = 0.0, faces: int = 0) -> FaceVerificationResult:
    return FaceVerificationResult(
        verified=False,
        person_id=ENROLLED_PERSON_ID,
        best_similarity=similarity,
        matched_template_index=-1,
        faces_detected=faces,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# STATUS TESTS (01 – 03)
# ---------------------------------------------------------------------------

class TestBiometricStatus:

    def test_01_person_enrolled(self):
        """Enrolled person returns enrolled=true with template_count and dim."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch.object(biometric_route_module._face_store, "get_templates",
                          return_value=_fake_templates(5, 512)):
            resp = client.get(f"/api/v1/biometric/status/{ENROLLED_PERSON_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["enrolled"] is True
        assert body["template_count"] == 5
        assert body["embedding_dimension"] == 512
        assert body["person_id"] == ENROLLED_PERSON_ID

    def test_02_person_not_enrolled(self):
        """Known person with no templates returns enrolled=false."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=False):
            resp = client.get(f"/api/v1/biometric/status/{ENROLLED_PERSON_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["enrolled"] is False
        assert body["template_count"] == 0

    def test_03_person_missing(self):
        """Unknown person_id returns 404."""
        resp = client.get(f"/api/v1/biometric/status/{UNKNOWN_PERSON_ID}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "PERSON_NOT_FOUND"


# ---------------------------------------------------------------------------
# ENROLL TESTS (04 – 10)
# ---------------------------------------------------------------------------

class TestBiometricEnroll:

    def _post(self, person_id: str = ENROLLED_PERSON_ID):
        return client.post("/api/v1/biometric/enroll", json={"person_id": person_id})

    def test_04_successful_enrollment(self):
        """Happy path: camera enrolls 5 samples, templates are saved and reloaded."""
        templates = _fake_templates(5, 512)
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.NOT_ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=False), \
             patch("atlas_ui.backend.routes.biometric.FaceEnrollmentService") as MockES, \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch.object(biometric_route_module._face_store, "get_templates",
                          return_value=templates):
            MockES.return_value.enroll_from_camera.return_value = _enroll_ok_result(5)
            resp = self._post()

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["samples_captured"] == 5
        assert body["template_count"] == 5
        assert body["embedding_dimension"] == 512
        assert body["reason"] == "ENROLLMENT_COMPLETED"

    def test_05_person_missing(self):
        """Unknown person_id returns 404."""
        resp = self._post(UNKNOWN_PERSON_ID)
        assert resp.status_code == 404
        assert resp.json()["reason"] == "PERSON_NOT_FOUND"

    def test_06_already_enrolled(self):
        """Person with existing templates returns 409 ALREADY_ENROLLED."""
        templates = _fake_templates(5, 512)
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch.object(biometric_route_module._face_store, "get_templates",
                          return_value=templates):
            resp = self._post()

        assert resp.status_code == 409
        assert resp.json()["reason"] == "ALREADY_ENROLLED"

    def test_07_camera_unavailable(self):
        """Camera open failure raises exception → 503 CAMERA_UNAVAILABLE."""
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.NOT_ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=False), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceEnrollmentService") as MockES:
            MockES.return_value.enroll_from_camera.side_effect = RuntimeError(
                "Camera source index 0 could not be initialized."
            )
            resp = self._post()

        assert resp.status_code == 503
        assert resp.json()["reason"] == "CAMERA_UNAVAILABLE"

    def test_08_insufficient_samples(self):
        """Enrollment that times out / collects < 5 samples returns 422."""
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.NOT_ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=False), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceEnrollmentService") as MockES:
            MockES.return_value.enroll_from_camera.return_value = _enroll_fail_result(
                reason="Timeout: only 3 of 5 required samples captured", captured=3
            )
            resp = self._post()

        assert resp.status_code == 422
        assert resp.json()["reason"] == "INSUFFICIENT_VALID_SAMPLES"

    def test_09_persistence_failure(self):
        """Enrollment fails during save → 500 PERSISTENCE_FAILURE."""
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.NOT_ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=False), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceEnrollmentService") as MockES:
            MockES.return_value.enroll_from_camera.return_value = _enroll_fail_result(
                reason="PERSISTENCE_FAILURE: could not write to disk"
            )
            resp = self._post()

        assert resp.status_code == 500
        assert resp.json()["reason"] == "PERSISTENCE_FAILURE"

    def test_10_camera_busy(self):
        """When the camera lock is held, a new enroll request returns 409 CAMERA_BUSY."""
        with patch.object(biometric_route_module._face_store, "get_template_status", return_value=TemplateStatus.NOT_ENROLLED), \
             patch.object(biometric_route_module._face_store, "has_templates", return_value=False):
            # Manually acquire the lock to simulate a concurrent operation
            acquired = biometric_route_module._camera_lock.acquire(blocking=False)
            assert acquired, "Lock should be free before the test"
            try:
                resp = self._post()
            finally:
                biometric_route_module._camera_lock.release()

        assert resp.status_code == 409
        assert resp.json()["reason"] == "CAMERA_BUSY"


# ---------------------------------------------------------------------------
# VERIFY TESTS (11 – 18)
# ---------------------------------------------------------------------------

class TestBiometricVerify:

    def _post(self, person_id: str = ENROLLED_PERSON_ID):
        return client.post("/api/v1/biometric/verify", json={"person_id": person_id})

    def test_11_successful_match(self):
        """Enrolled person verified → 200 with verified=True, reason=MATCH."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
            MockVS.return_value.verify_from_camera.return_value = _verify_match_result(0.85)
            resp = self._post()

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["verified"] is True
        assert body["reason"] == "MATCH"
        assert body["best_similarity"] == pytest.approx(0.85, abs=1e-4)

    def test_12_failed_match(self):
        """Low similarity → 200 with verified=False, reason=NO_MATCH."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
            MockVS.return_value.verify_from_camera.return_value = _verify_fail_result(
                "NO_MATCH (median similarity 0.32 < threshold 0.65)", similarity=0.32
            )
            resp = self._post()

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is False
        assert body["reason"] == "NO_MATCH"

    def test_13_no_biometric_enrollment(self):
        """Person exists but has no templates → 400 NO_BIOMETRIC_ENROLLMENT."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=False):
            resp = self._post()

        assert resp.status_code == 400
        assert resp.json()["reason"] == "NO_BIOMETRIC_ENROLLMENT"

    def test_14_person_missing(self):
        """Unknown person_id → 404 PERSON_NOT_FOUND."""
        resp = self._post(UNKNOWN_PERSON_ID)
        assert resp.status_code == 404
        assert resp.json()["reason"] == "PERSON_NOT_FOUND"

    def test_15_no_face(self):
        """Camera sees no face → 200 verified=False reason=NO_FACE."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
            MockVS.return_value.verify_from_camera.return_value = _verify_fail_result(
                "Timeout: NO_FACE", faces=0
            )
            resp = self._post()

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is False
        assert body["reason"] == "NO_FACE"

    def test_16_multiple_faces(self):
        """Camera sees multiple faces → 200 verified=False reason=MULTIPLE_FACES."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
            MockVS.return_value.verify_from_camera.return_value = _verify_fail_result(
                "Timeout: MULTIPLE_FACES", faces=2
            )
            resp = self._post()

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is False
        assert body["reason"] == "MULTIPLE_FACES"

    def test_17_camera_unavailable(self):
        """Camera open throws → 503 CAMERA_UNAVAILABLE."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
             patch("atlas_ui.backend.routes.biometric.YOLOFaceDetector"), \
             patch("atlas_ui.backend.routes.biometric.InsightFaceRecognizer"), \
             patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
            MockVS.return_value.verify_from_camera.side_effect = RuntimeError(
                "Camera source index 0 could not be initialized."
            )
            resp = self._post()

        assert resp.status_code == 503
        assert resp.json()["reason"] == "CAMERA_UNAVAILABLE"

    def test_18_camera_busy(self):
        """When the camera lock is held, verify returns 409 CAMERA_BUSY."""
        with patch.object(biometric_route_module._face_store, "has_templates", return_value=True):
            acquired = biometric_route_module._camera_lock.acquire(blocking=False)
            assert acquired, "Lock should be free before the test"
            try:
                resp = self._post()
            finally:
                biometric_route_module._camera_lock.release()

        assert resp.status_code == 409
        assert resp.json()["reason"] == "CAMERA_BUSY"


# ---------------------------------------------------------------------------
# RESET TESTS
# ---------------------------------------------------------------------------

class TestBiometricReset:

    def test_reset_successful(self):
        """Happy path: credentials match, templates removed, status updated."""
        from atlas_ui.backend.routes.biometric import _face_store
        
        with patch.object(client.app.state.credential_verifier, "verify_credentials") as mock_verify, \
             patch.object(client.app.state.person_registry, "get_person_by_account") as mock_get_person, \
             patch.object(_face_store, "remove_templates") as mock_remove, \
             patch.object(client.app.state.person_registry, "update_person") as mock_update:
            
            from unittest.mock import MagicMock
            mock_acc = MagicMock()
            mock_acc.account_id = "test_acc_id"
            mock_verify.return_value = mock_acc
            
            mock_person = MagicMock()
            mock_person.atlas_person_id = "test_person_id"
            mock_get_person.return_value = mock_person
            
            resp = client.post("/api/v1/biometric/reset", json={
                "username": "test_user",
                "password": "test_password"
            })
            
            assert resp.status_code == 200
            assert resp.json() == {
                "success": True,
                "message": "Biometric profile has been successfully reset. Please log in to configure new templates."
            }
            mock_verify.assert_called_once_with("test_user", "test_password")
            mock_get_person.assert_called_once_with("test_acc_id")
            mock_remove.assert_called_once_with("test_person_id")
            mock_update.assert_called_once_with("test_person_id", face_enrollment_status="NOT_ENROLLED")

    def test_reset_invalid_credentials(self):
        """Incorrect credentials returns 401."""
        with patch.object(client.app.state.credential_verifier, "verify_credentials", side_effect=ValueError("Invalid password")):
            resp = client.post("/api/v1/biometric/reset", json={
                "username": "test_user",
                "password": "wrong_password"
            })
            
            assert resp.status_code == 401
            assert resp.json()["success"] is False
            assert "Invalid" in resp.json()["message"]

    def test_reset_no_person_profile(self):
        """No associated person profile returns 404."""
        with patch.object(client.app.state.credential_verifier, "verify_credentials") as mock_verify, \
             patch.object(client.app.state.person_registry, "get_person_by_account", return_value=None):
            
            from unittest.mock import MagicMock
            mock_acc = MagicMock()
            mock_acc.account_id = "test_acc_id"
            mock_verify.return_value = mock_acc
            
            resp = client.post("/api/v1/biometric/reset", json={
                "username": "test_user",
                "password": "test_password"
            })
            
            assert resp.status_code == 404
            assert resp.json()["success"] is False

    def test_reset_already_reset(self):
        """Resetting when no templates exist is handled gracefully (idempotent 200)."""
        from atlas_ui.backend.routes.biometric import _face_store
        
        with patch.object(client.app.state.credential_verifier, "verify_credentials") as mock_verify, \
             patch.object(client.app.state.person_registry, "get_person_by_account") as mock_get_person, \
             patch.object(_face_store, "remove_templates", return_value=False) as mock_remove, \
             patch.object(client.app.state.person_registry, "update_person") as mock_update:
            
            from unittest.mock import MagicMock
            mock_acc = MagicMock()
            mock_acc.account_id = "test_acc_id"
            mock_verify.return_value = mock_acc
            
            mock_person = MagicMock()
            mock_person.atlas_person_id = "test_person_id"
            mock_get_person.return_value = mock_person
            
            resp = client.post("/api/v1/biometric/reset", json={
                "username": "test_user",
                "password": "test_password"
            })
            
            assert resp.status_code == 200
            assert resp.json()["success"] is True
            mock_remove.assert_called_once_with("test_person_id")
            mock_update.assert_called_once_with("test_person_id", face_enrollment_status="NOT_ENROLLED")


