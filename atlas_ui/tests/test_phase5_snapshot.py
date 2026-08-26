"""
Phase 5 — Biometric Verification Snapshot Tests

Tests:
    P5-01  Successful verification → snapshot written to VerificationSnapshotStore
    P5-02  Successful verification + store raises → auth still succeeds (non-fatal)
    P5-03  Failed verification → snapshot store never called
    P5-04  Admin retrieves snapshot by ID → 200
    P5-05  Admin lists snapshots for a person → 200
    P5-06  Non-admin session → 403 on snapshot retrieval
    P5-07  Missing snapshot ID → 404
    P5-08  Unknown person_id for list endpoint → 404

Requirements validated:
    * Reuses the frame already captured for biometric verification (no extra camera).
    * Does NOT interfere with the existing YOLO or InsightFace pipeline.
    * Snapshot storage failure NEVER changes a successful auth to a failure.
    * Only sessions with MANAGE_USERS permission can retrieve snapshots.
    * Normal users cannot access other users' verification images.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from atlas_ui.backend.main import app
from atlas_ui.backend.vision.face_verification_service import FaceVerificationResult
from atlas_ui.backend.models.snapshot import VerificationSnapshot
from atlas_ui.backend.vision.verification_snapshot_store import VerificationSnapshotStore
import atlas_ui.backend.routes.biometric as biometric_route_module

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)

ENROLLED_PERSON_ID = "ATLAS-P-88888888"   # seeded by main.py (ADMIN person)
USER_PERSON_ID     = "ATLAS-P-11111111"   # seeded by main.py (USER person)
UNKNOWN_PERSON_ID  = "ATLAS-P-99999999"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verify_match_result(similarity: float = 0.85) -> FaceVerificationResult:
    return FaceVerificationResult(
        verified=True,
        person_id=ENROLLED_PERSON_ID,
        best_similarity=similarity,
        matched_template_index=0,
        faces_detected=1,
        reason="MATCH",
    )


def _verify_fail_result(reason: str = "NO_MATCH", similarity: float = 0.3) -> FaceVerificationResult:
    return FaceVerificationResult(
        verified=False,
        person_id=ENROLLED_PERSON_ID,
        best_similarity=similarity,
        matched_template_index=-1,
        faces_detected=1,
        reason=reason,
    )


def _make_snapshot(
    person_id: str = ENROLLED_PERSON_ID,
    result: str = "MATCH",
) -> VerificationSnapshot:
    """Create a concrete VerificationSnapshot for injection into tests."""
    return VerificationSnapshot(
        person_id=person_id,
        result=result,
        score=0.85,
        account_id="test_account",
        session_id=None,
        thumbnail_b64=None,
    )


def _admin_session_headers() -> dict:
    """
    Return headers that carry a valid ADMIN session token.

    Uses the same two-step pattern as test_authorization.py:
    1. POST /login → gets biometric_required + person_id
    2. register_biometric_success() to mint a one-time token
    3. POST /login again with the biometric token → gets session_id
    """
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123",
    })
    data = login_resp.json()
    if data.get("biometric_required"):
        person_id = data["person_id"]
        token = "test_verify_token_admin"
        app.state.auth_service.register_biometric_success(person_id, token)
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin_user",
            "password": "admin_pass_123",
            "biometric_input": token,
        })
        data = login_resp.json()
    assert data.get("session_id"), f"Admin login failed: {login_resp.text}"
    return {"Authorization": f"Bearer {data['session_id']}"}


def _user_session_headers() -> dict:
    """Return headers that carry a valid USER (non-admin) session token."""
    login_resp = client.post("/api/v1/auth/login", json={
        "username": "normal_user",
        "password": "user_pass_123",
    })
    data = login_resp.json()
    if data.get("biometric_required"):
        person_id = data["person_id"]
        token = "test_verify_token_user"
        app.state.auth_service.register_biometric_success(person_id, token)
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "normal_user",
            "password": "user_pass_123",
            "biometric_input": token,
        })
        data = login_resp.json()
    assert data.get("session_id"), f"User login failed: {login_resp.text}"
    return {"Authorization": f"Bearer {data['session_id']}"}


# ---------------------------------------------------------------------------
# P5-01  Successful verification → snapshot written
# ---------------------------------------------------------------------------

class TestSnapshotOnSuccessfulVerification:

    def test_p5_01_snapshot_stored_on_successful_verification(self):
        """
        When biometric verification succeeds, the snapshot store's store()
        method is called exactly once with a VerificationSnapshot whose
        person_id matches the verified person.

        The API must still return verified=True.
        """
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)
        mock_snap_store.store.return_value = "fake-snapshot-uuid"

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        try:
            with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
                 patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
                MockVS.return_value.verify_from_camera.return_value = _verify_match_result(0.87)

                resp = client.post(
                    "/api/v1/biometric/verify",
                    json={"person_id": ENROLLED_PERSON_ID},
                )
        finally:
            # Restore real store so other tests are not affected
            app.state.snapshot_store = original_snap_store

        # Auth outcome
        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True
        assert body["reason"] == "MATCH"

        # Snapshot written exactly once
        mock_snap_store.store.assert_called_once()
        stored_snap: VerificationSnapshot = mock_snap_store.store.call_args[0][0]
        assert stored_snap.person_id == ENROLLED_PERSON_ID
        assert stored_snap.result == "MATCH"
        assert stored_snap.score == pytest.approx(0.87, abs=1e-4)


# ---------------------------------------------------------------------------
# P5-02  Storage failure is non-fatal
# ---------------------------------------------------------------------------

class TestSnapshotStorageFailureNonFatal:

    def test_p5_02_storage_failure_does_not_affect_auth(self):
        """
        When VerificationSnapshotStore.store() raises an exception during a
        successful biometric verification, the API must still return
        verified=True.  The snapshot error must NEVER become a biometric failure.
        """
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)
        mock_snap_store.store.side_effect = RuntimeError("Disk full / simulated store failure")

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        try:
            with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
                 patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
                MockVS.return_value.verify_from_camera.return_value = _verify_match_result(0.90)

                resp = client.post(
                    "/api/v1/biometric/verify",
                    json={"person_id": ENROLLED_PERSON_ID},
                )
        finally:
            app.state.snapshot_store = original_snap_store

        # The store threw, but the auth result must still be a success
        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is True, (
            "Storage failure must not flip a successful biometric verification to failed"
        )
        assert body["reason"] == "MATCH"

        # store() was still called (we tried) — the exception was swallowed
        mock_snap_store.store.assert_called_once()


# ---------------------------------------------------------------------------
# P5-03  Failed verification → snapshot store never called
# ---------------------------------------------------------------------------

class TestNoSnapshotOnFailedVerification:

    def test_p5_03_no_snapshot_on_failed_verification(self):
        """
        When biometric verification fails (verified=False), the snapshot store
        must NOT be written to.
        """
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        try:
            with patch.object(biometric_route_module._face_store, "has_templates", return_value=True), \
                 patch("atlas_ui.backend.routes.biometric.FaceVerificationService") as MockVS:
                MockVS.return_value.verify_from_camera.return_value = _verify_fail_result(
                    "NO_MATCH (median similarity 0.31 < threshold 0.65)", 0.31
                )

                resp = client.post(
                    "/api/v1/biometric/verify",
                    json={"person_id": ENROLLED_PERSON_ID},
                )
        finally:
            app.state.snapshot_store = original_snap_store

        assert resp.status_code == 200
        body = resp.json()
        assert body["verified"] is False
        assert body["reason"] == "NO_MATCH"

        # store() must NOT have been called for a failed verification
        mock_snap_store.store.assert_not_called()


# ---------------------------------------------------------------------------
# P5-04  Admin retrieves snapshot by ID → 200
# ---------------------------------------------------------------------------

class TestSnapshotRetrievalByAdmin:

    def test_p5_04_admin_can_retrieve_snapshot_by_id(self):
        """
        An admin session can retrieve a known snapshot via
        GET /api/v1/admin/snapshots/{snapshot_id}.
        The response includes person_id, result, score, and thumbnail_b64.
        """
        snap = _make_snapshot()
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)
        mock_snap_store.get.return_value = snap

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        headers = _admin_session_headers()
        try:
            resp = client.get(
                f"/api/v1/admin/snapshots/{snap.snapshot_id}",
                headers=headers,
            )
        finally:
            app.state.snapshot_store = original_snap_store

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["snapshot_id"] == snap.snapshot_id
        assert body["person_id"] == ENROLLED_PERSON_ID
        assert body["result"] == "MATCH"
        assert body["score"] == pytest.approx(0.85, abs=1e-4)
        # thumbnail_b64 key must be present (None in this minimal snapshot)
        assert "thumbnail_b64" in body


# ---------------------------------------------------------------------------
# P5-05  Admin lists snapshots for a person → 200
# ---------------------------------------------------------------------------

class TestSnapshotListByAdmin:

    def test_p5_05_admin_can_list_snapshots_for_person(self):
        """
        GET /api/v1/admin/people/{person_id}/snapshots returns a list of
        snapshot metadata records (no thumbnail by default) for a known person.
        """
        snap = _make_snapshot()
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)
        mock_snap_store.list_for_person.return_value = [
            {
                "snapshot_id":   snap.snapshot_id,
                "person_id":     snap.person_id,
                "account_id":    snap.account_id,
                "session_id":    snap.session_id,
                "timestamp":     snap.timestamp,
                "result":        snap.result,
                "score":         snap.score,
                "has_thumbnail": False,
            }
        ]

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        headers = _admin_session_headers()
        try:
            resp = client.get(
                f"/api/v1/admin/people/{ENROLLED_PERSON_ID}/snapshots",
                headers=headers,
            )
        finally:
            app.state.snapshot_store = original_snap_store

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["person_id"] == ENROLLED_PERSON_ID
        assert body["total"] == 1
        assert len(body["snapshots"]) == 1
        assert body["snapshots"][0]["snapshot_id"] == snap.snapshot_id
        # Thumbnail must be omitted by default (has_thumbnail flag present instead)
        assert "thumbnail_b64" not in body["snapshots"][0]

        # Verify the store was asked without include_image
        mock_snap_store.list_for_person.assert_called_once_with(
            ENROLLED_PERSON_ID, include_image=False
        )


# ---------------------------------------------------------------------------
# P5-06  Non-admin session → 403
# ---------------------------------------------------------------------------

class TestSnapshotAuthorizationProtection:

    def test_p5_06a_non_admin_cannot_retrieve_snapshot(self):
        """
        A USER-role session must receive HTTP 403 when attempting to access
        GET /api/v1/admin/snapshots/{snapshot_id}.
        Normal users cannot retrieve any user's verification images.
        """
        headers = _user_session_headers()
        resp = client.get(
            "/api/v1/admin/snapshots/any-snapshot-id",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text
        assert "Forbidden" in resp.json().get("error", "")

    def test_p5_06b_non_admin_cannot_list_snapshots(self):
        """
        A USER-role session must receive HTTP 403 when accessing
        GET /api/v1/admin/people/{person_id}/snapshots.
        """
        headers = _user_session_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ENROLLED_PERSON_ID}/snapshots",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_p5_06c_unauthenticated_cannot_access_snapshots(self):
        """
        Requests without any session token must receive HTTP 401.
        """
        resp = client.get("/api/v1/admin/snapshots/any-snapshot-id")
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# P5-07  Missing snapshot ID → 404
# ---------------------------------------------------------------------------

class TestSnapshotNotFound:

    def test_p5_07_unknown_snapshot_id_returns_404(self):
        """
        When the snapshot_id is not found in the store (never created or
        evicted from the ring buffer), the endpoint returns 404.
        """
        mock_snap_store = MagicMock(spec=VerificationSnapshotStore)
        mock_snap_store.get.return_value = None   # not found

        original_snap_store = getattr(app.state, "snapshot_store", None)
        app.state.snapshot_store = mock_snap_store

        headers = _admin_session_headers()
        try:
            resp = client.get(
                "/api/v1/admin/snapshots/does-not-exist-uuid",
                headers=headers,
            )
        finally:
            app.state.snapshot_store = original_snap_store

        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["error"].lower()


# ---------------------------------------------------------------------------
# P5-08  Unknown person_id for list endpoint → 404
# ---------------------------------------------------------------------------

class TestSnapshotListPersonNotFound:

    def test_p5_08_list_snapshots_unknown_person_returns_404(self):
        """
        The list endpoint validates the person_id against PersonRegistry.
        Requesting snapshots for an unknown person_id returns 404.
        """
        headers = _admin_session_headers()
        resp = client.get(
            f"/api/v1/admin/people/{UNKNOWN_PERSON_ID}/snapshots",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["error"].lower()
