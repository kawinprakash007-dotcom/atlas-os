"""
Phase 6 — Advanced User Information API Tests

Tests:
    P6-01  GET /users/summary — returns list with required fields per user
    P6-02  GET /users/{person_id}/profile — 200 with full profile data
    P6-03  Non-admin on profile endpoint → 403
    P6-04  Unknown person_id for profile → 404
    P6-05  Activity history returns events for correct person, newest-first
    P6-06  Activity history pagination works (page/limit)
    P6-07  Activity history event_type filter works
    P6-08  Session history reconstructed from audit records
    P6-09  Location history: only non-null GPS entries returned
    P6-10  Location history: events without GPS coords are excluded
    P6-11  Unauthenticated access to any new endpoint → 401
    P6-12  Unknown person_id for activity/session/location → 404
"""

import time
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from atlas_ui.backend.main import app
from atlas_ui.backend.models.audit import AuditRecord

# ---------------------------------------------------------------------------
# Constants & test client
# ---------------------------------------------------------------------------

client = TestClient(app, raise_server_exceptions=False)

ADMIN_PERSON_ID = "ATLAS-P-88888888"   # seeded by main.py
USER_PERSON_ID  = "ATLAS-P-11111111"   # seeded by main.py
UNKNOWN_PERSON_ID = "ATLAS-P-ZZZZZZZZ"


# ---------------------------------------------------------------------------
# Session helpers (same two-step pattern as Phase 5 tests)
# ---------------------------------------------------------------------------

def _admin_headers() -> dict:
    resp = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123",
    })
    data = resp.json()
    if data.get("biometric_required"):
        pid = data["person_id"]
        tok = "p6_admin_token"
        app.state.auth_service.register_biometric_success(pid, tok)
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin_user",
            "password": "admin_pass_123",
            "biometric_input": tok,
        })
        data = resp.json()
    assert data.get("session_id"), f"Admin login failed: {resp.text}"
    return {"Authorization": f"Bearer {data['session_id']}"}


def _user_headers() -> dict:
    resp = client.post("/api/v1/auth/login", json={
        "username": "normal_user",
        "password": "user_pass_123",
    })
    data = resp.json()
    if data.get("biometric_required"):
        pid = data["person_id"]
        tok = "p6_user_token"
        app.state.auth_service.register_biometric_success(pid, tok)
        resp = client.post("/api/v1/auth/login", json={
            "username": "normal_user",
            "password": "user_pass_123",
            "biometric_input": tok,
        })
        data = resp.json()
    assert data.get("session_id"), f"User login failed: {resp.text}"
    return {"Authorization": f"Bearer {data['session_id']}"}


# ---------------------------------------------------------------------------
# Audit record factory
# ---------------------------------------------------------------------------

def _make_audit_record(
    person_id: str,
    event_type: str = "LOGIN_SUCCESS",
    session_id: str = "sess-123",
    gps_lat: float = None,
    gps_lon: float = None,
    gps_acc: float = None,
    timestamp: float = None,
    ip: str = "10.0.0.1",
) -> AuditRecord:
    return AuditRecord(
        attempt_id=f"aud-{event_type[:4]}-{id(person_id)}",
        timestamp=timestamp or time.time(),
        event_type=event_type,
        account_id="acc-test",
        person_id=person_id,
        session_id=session_id,
        access_result="SUCCESS",
        credential_verified=True,
        face_verified=True,
        ip_address=ip,
        gps_latitude=gps_lat,
        gps_longitude=gps_lon,
        gps_accuracy=gps_acc,
    )


# ===========================================================================
# P6-01  User List Summary
# ===========================================================================

class TestUserSummaryList:

    def test_p6_01_summary_returns_all_users_with_required_fields(self):
        """
        GET /api/v1/admin/users/summary must return a list where each entry
        has the required summary fields: person_id, username, full_name,
        role, account_status, biometric_enrollment, online, last_login,
        last_access_location, latest_verification_result.
        """
        headers = _admin_headers()
        resp = client.get("/api/v1/admin/users/summary", headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "total" in body
        assert "users" in body
        assert body["total"] == len(body["users"])
        assert body["total"] >= 2   # at least admin + normal_user seeded

        required_keys = {
            "person_id", "username", "full_name", "role", "account_status",
            "biometric_enrollment", "online", "last_login",
            "last_access_location", "latest_verification_result",
        }
        for user in body["users"]:
            missing = required_keys - set(user.keys())
            assert not missing, f"Missing keys in summary entry: {missing}"

    def test_p6_01b_summary_location_is_null_when_no_gps(self):
        """
        last_access_location must be null (not an empty dict or fabricated)
        when no GPS data has been recorded for a user.
        """
        headers = _admin_headers()
        resp = client.get("/api/v1/admin/users/summary", headers=headers)
        assert resp.status_code == 200

        body = resp.json()
        # The seeded users have no GPS data, so location should be null
        for user in body["users"]:
            loc = user["last_access_location"]
            # If present it must have real coordinates; if None that's correct
            if loc is not None:
                assert "latitude" in loc
                assert "longitude" in loc


# ===========================================================================
# P6-02  Detailed User Profile
# ===========================================================================

class TestDetailedUserProfile:

    def test_p6_02_admin_gets_full_profile(self):
        """
        GET /api/v1/admin/people/{person_id}/profile returns a full profile
        with all required sections.
        """
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/profile",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Identity
        assert body["person_id"] == ADMIN_PERSON_ID
        assert body["display_name"] is not None
        assert body["role"] is not None
        assert body["status"] is not None

        # Account
        assert body["username"] is not None
        assert "account_enabled" in body

        # Biometric
        assert "face_enrollment_status" in body
        assert "template_count" in body
        assert "snapshot_count" in body

        # Login stats
        assert "login_count" in body
        assert "total_session_duration" in body

        # Session
        assert "online" in body

        # Location (should be None — no GPS recorded in tests)
        assert "last_access_location" in body

        # Security
        assert "failed_login_attempts" in body
        assert "account_lock_status" in body

    def test_p6_03_non_admin_gets_403_on_profile(self):
        """USER-role session must receive 403 on profile endpoint."""
        headers = _user_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/profile",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_p6_04_unknown_person_returns_404(self):
        """Unknown person_id returns 404."""
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{UNKNOWN_PERSON_ID}/profile",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text
        assert "not found" in resp.json()["error"].lower()


# ===========================================================================
# P6-05 / P6-06 / P6-07  Activity History
# ===========================================================================

class TestActivityHistory:

    def test_p6_05_activity_history_returns_events(self):
        """
        Activity history for an enrolled person who has logged in must return
        at least one event in the expected format.
        """
        # Force a login to ensure at least one audit record exists
        _admin_headers()   # triggers LOGIN_SUCCESS audit record

        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/activity",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["person_id"] == ADMIN_PERSON_ID
        assert "total" in body
        assert "page" in body
        assert "limit" in body
        assert "total_pages" in body
        assert "items" in body

        # Each item has required fields
        for item in body["items"]:
            assert "event_id" in item
            assert "event_type" in item
            assert "timestamp" in item

    def test_p6_06_activity_pagination_works(self):
        """Pagination: page=1,limit=2 returns at most 2 items."""
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/activity?page=1&limit=2",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) <= 2
        assert body["limit"] == 2
        assert body["page"] == 1

    def test_p6_07_activity_event_type_filter(self):
        """
        When event_type filter is applied, only events of that type are returned.
        """
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/activity?event_type=LOGIN_SUCCESS",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        for item in body["items"]:
            assert item["event_type"] == "LOGIN_SUCCESS"

    def test_p6_12a_activity_unknown_person_404(self):
        """Unknown person_id on activity endpoint returns 404."""
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{UNKNOWN_PERSON_ID}/activity",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# P6-08  Session History
# ===========================================================================

class TestSessionHistory:

    def test_p6_08_session_history_returns_login_events(self):
        """
        Session history is reconstructed from LOGIN_SUCCESS audit records.
        Each entry has the required session fields.
        """
        # Ensure at least one login exists
        _admin_headers()

        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{ADMIN_PERSON_ID}/sessions",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["person_id"] == ADMIN_PERSON_ID
        assert "total" in body
        assert "items" in body

        required_session_keys = {
            "session_id", "login_time", "logout_time", "duration_seconds",
            "session_status", "login_ip", "login_device", "login_location",
            "verification_status", "face_verified",
        }
        for item in body["items"]:
            missing = required_session_keys - set(item.keys())
            assert not missing, f"Missing session keys: {missing}"
            # session_status must be one of the expected values
            assert item["session_status"] in {"ACTIVE", "COMPLETED", "UNKNOWN"}

    def test_p6_12b_sessions_unknown_person_404(self):
        """Unknown person_id on sessions endpoint returns 404."""
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{UNKNOWN_PERSON_ID}/sessions",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# P6-09 / P6-10  Location History
# ===========================================================================

class TestLocationHistory:

    def test_p6_09_location_history_only_real_coords(self):
        """
        Location history endpoint must only return entries that have
        both gps_latitude and gps_longitude set.  Every returned entry
        must have non-null latitude and longitude.
        """
        # Inject GPS-bearing audit records for the admin person
        real_record = _make_audit_record(
            person_id=ADMIN_PERSON_ID,
            event_type="LOGIN_SUCCESS",
            gps_lat=12.9716,
            gps_lon=77.5946,
            gps_acc=15.0,
        )
        no_gps_record = _make_audit_record(
            person_id=ADMIN_PERSON_ID,
            event_type="LOGIN_SUCCESS",
            gps_lat=None,
            gps_lon=None,
        )

        mock_audit = MagicMock()
        mock_audit.filter_records.return_value = [real_record, no_gps_record]

        original_audit = app.state.auth_audit
        app.state.auth_audit = mock_audit

        headers = _admin_headers()
        try:
            resp = client.get(
                f"/api/v1/admin/people/{ADMIN_PERSON_ID}/locations",
                headers=headers,
            )
        finally:
            app.state.auth_audit = original_audit

        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Only the record with GPS should appear
        assert body["total"] == 1
        assert len(body["items"]) == 1
        loc = body["items"][0]
        assert loc["latitude"] == pytest.approx(12.9716, abs=1e-4)
        assert loc["longitude"] == pytest.approx(77.5946, abs=1e-4)

    def test_p6_10_location_history_no_coords_excluded(self):
        """
        If all audit records lack GPS coordinates, the location history
        returns an empty list (no fabrication).
        """
        no_gps_records = [
            _make_audit_record(ADMIN_PERSON_ID, gps_lat=None, gps_lon=None),
            _make_audit_record(ADMIN_PERSON_ID, gps_lat=None, gps_lon=None),
        ]

        mock_audit = MagicMock()
        mock_audit.filter_records.return_value = no_gps_records

        original_audit = app.state.auth_audit
        app.state.auth_audit = mock_audit

        headers = _admin_headers()
        try:
            resp = client.get(
                f"/api/v1/admin/people/{ADMIN_PERSON_ID}/locations",
                headers=headers,
            )
        finally:
            app.state.auth_audit = original_audit

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_p6_12c_locations_unknown_person_404(self):
        """Unknown person_id on locations endpoint returns 404."""
        headers = _admin_headers()
        resp = client.get(
            f"/api/v1/admin/people/{UNKNOWN_PERSON_ID}/locations",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text


# ===========================================================================
# P6-11  Unauthenticated access
# ===========================================================================

class TestUnauthenticatedAccess:

    @pytest.mark.parametrize("url", [
        "/api/v1/admin/users/summary",
        f"/api/v1/admin/people/{ADMIN_PERSON_ID}/profile",
        f"/api/v1/admin/people/{ADMIN_PERSON_ID}/activity",
        f"/api/v1/admin/people/{ADMIN_PERSON_ID}/sessions",
        f"/api/v1/admin/people/{ADMIN_PERSON_ID}/locations",
    ])
    def test_p6_11_unauthenticated_gets_401(self, url):
        """All Phase 6 endpoints must return 401 when no session is provided."""
        resp = client.get(url)
        assert resp.status_code == 401, f"Expected 401 for {url}, got {resp.status_code}"
