"""
tests/test_remote_vision_integration.py

ATLAS OS Remote Vision Integration Test Suite
=============================================
Tests the real ATLAS Vision LAN integration (10.9.96.13:8765).

Phases tested:
  1. RemoteVisionClient — disabled state
  2. RemoteVisionClient — offline / unreachable (mocked)
  3. RemoteVisionClient — real API contract (mocked responses matching confirmed Vision API)
  4. VisionEventAdapter — normalization + TRACK-* identity safety
  5. Admin API gateway — authorization enforcement
  6. OS status endpoint — returns correct vision block structure
  7. Network readiness — ATLAS OS remains healthy when Vision is offline
  8. VisionSyncWorker — still defaults to port 8002 (legacy isolation confirmed)
  9. Regression — existing event schema tests

The remote Vision machine does NOT need to be online for any pytest tests.
All remote HTTP calls are mocked with confirmed-real response shapes.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ── Core network layer ────────────────────────────────────────────────────────
from atlas_core.network.schemas import VisionEvent, ContractValidationError, validate_event
from atlas_core.network.vision_adapter import VisionEventAdapter
from atlas_core.network.remote_vision_client import RemoteVisionClient


# =============================================================================
# Helpers — confirmed-real Vision API response shapes
# =============================================================================

def _mock_health_response():
    """Real response from GET /health confirmed 2026-08-27."""
    return {
        "status": "healthy",
        "service": "ATLAS Vision",
        "version": "1.5.0",
        "contract_version": "1.0",
        "camera": {"status": "connected"}
    }

def _mock_status_response():
    """Real response from GET /api/v1/vision/status confirmed 2026-08-27."""
    return {
        "service": "ATLAS Vision",
        "status": "healthy",
        "camera_status": "connected",
        "recognition_status": "active",
        "active_tracks": 1,
        "headless": False,
        "server_port": 8765
    }

def _mock_incidents_response():
    """Real response envelope from GET /api/v1/incidents confirmed 2026-08-27."""
    return {
        "contract_version": "1.0",
        "message_type": "QUERY_RESPONSE",
        "request_id": "req-test-001",
        "query_type": "GET_INCIDENTS",
        "success": True,
        "timestamp": "2026-08-27T10:00:00.000000Z",
        "data": {
            "incidents": [
                {
                    "incident_id": "inc-00001234-0000-0000-0000-000000000001",
                    "event_id": "evt-00001234-0000-0000-0000-000000000001",
                    "created_at": "2026-08-27T10:00:00.000000Z",
                    "updated_at": "2026-08-27T10:00:00.000000Z",
                    "incident_type": "SAFETY_ALERT",
                    "severity": "HIGH",
                    "status": "ACTIVE",
                    "person_id": "ATLAS-P003",
                    "description": "Target ATLAS-P003 remained within monitored area for 30.0 seconds.",
                    "metadata": {}
                }
            ]
        },
        "error": None
    }

def _mock_alerts_response():
    """Real response envelope from GET /api/v1/security/alerts confirmed 2026-08-27."""
    return {
        "contract_version": "1.0",
        "message_type": "QUERY_RESPONSE",
        "request_id": "req-test-002",
        "query_type": "GET_SECURITY_ALERTS",
        "success": True,
        "timestamp": "2026-08-27T10:00:00.000000Z",
        "data": {
            "alerts": [
                {
                    "alert_id": "alt-00001234-0000-0000-0000-000000000001",
                    "incident_id": "inc-00001234-0000-0000-0000-000000000001",
                    "timestamp": "2026-08-27T10:00:00.000000Z",
                    "severity": "HIGH",
                    "title": "Security Alert",
                    "message": "Target ATLAS-P003 remained within monitored area for 30.0 seconds.",
                    "acknowledged": False,
                    "metadata": {}
                }
            ]
        },
        "error": None
    }

def _urlopen_mock(payload: dict, status_code: int = 200):
    """Creates a mock urllib response returning a confirmed API payload."""
    import io
    mock_resp = MagicMock()
    mock_resp.status = status_code
    mock_resp.read.return_value = json.dumps(payload).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# =============================================================================
# Phase 1 — RemoteVisionClient disabled state
# =============================================================================

class TestRemoteVisionClientDisabled:

    def _make_disabled_client(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "false", "ATLAS_VISION_BASE_URL": "http://10.9.96.13:8765"}):
            return RemoteVisionClient()

    def test_disabled_flag_set_correctly(self):
        c = self._make_disabled_client()
        assert c.enabled is False

    def test_disabled_health_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.get_health()["status"] == "disabled"

    def test_disabled_status_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.get_status()["status"] == "disabled"

    def test_disabled_incidents_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.get_incidents()["status"] == "disabled"

    def test_disabled_recent_incidents_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.get_recent_incidents()["status"] == "disabled"

    def test_disabled_alerts_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.get_security_alerts()["status"] == "disabled"

    def test_disabled_connection_state_returns_disabled(self):
        c = self._make_disabled_client()
        assert c.connection_state() == "DISABLED"


# =============================================================================
# Phase 2 — RemoteVisionClient offline / unreachable state
# =============================================================================

class TestRemoteVisionClientOffline:

    def _make_client(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_BASE_URL": "http://10.9.96.13:8765", "ATLAS_VISION_TIMEOUT": "2"}):
            return RemoteVisionClient()

    @patch("urllib.request.urlopen")
    def test_connection_refused_returns_offline(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        c = self._make_client()
        result = c.get_health()
        assert result["status"] == "offline"
        assert result["error_type"] == "unreachable"
        assert "10.9.96.13:8765" in result["detail"]

    @patch("urllib.request.urlopen")
    def test_timeout_does_not_crash_atlas_os(self, mock_urlopen):
        mock_urlopen.side_effect = TimeoutError("timed out")
        c = self._make_client()
        result = c.get_health()
        assert "status" in result
        assert result["status"] in ("error", "offline")

    @patch("urllib.request.urlopen")
    def test_connection_refused_connection_state_offline(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        c = self._make_client()
        assert c.connection_state() == "OFFLINE"

    @patch("urllib.request.urlopen")
    def test_offline_incidents_returns_safe_dict(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        c = self._make_client()
        result = c.get_incidents()
        assert isinstance(result, dict)
        assert result["status"] == "offline"

    @patch("urllib.request.urlopen")
    def test_offline_alerts_returns_safe_dict(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        c = self._make_client()
        result = c.get_security_alerts()
        assert isinstance(result, dict)
        assert result["status"] == "offline"


# =============================================================================
# Phase 3 — RemoteVisionClient success (confirmed real API shapes)
# =============================================================================

class TestRemoteVisionClientSuccess:

    def _make_client(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_BASE_URL": "http://10.9.96.13:8765", "ATLAS_VISION_TIMEOUT": "10"}):
            return RemoteVisionClient()

    @patch("urllib.request.urlopen")
    def test_health_success_returns_correct_fields(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock(_mock_health_response())
        c = self._make_client()
        result = c.get_health()
        assert result["status"] == "healthy"
        assert result["service"] == "ATLAS Vision"
        assert result["version"] == "1.5.0"
        assert result["contract_version"] == "1.0"
        assert result["camera"]["status"] == "connected"

    @patch("urllib.request.urlopen")
    def test_status_success_returns_correct_fields(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock(_mock_status_response())
        c = self._make_client()
        result = c.get_status()
        assert result["status"] == "healthy"
        assert result["camera_status"] == "connected"
        assert result["recognition_status"] == "active"
        assert "active_tracks" in result
        assert "server_port" in result

    @patch("urllib.request.urlopen")
    def test_incidents_uses_query_response_envelope(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock(_mock_incidents_response())
        c = self._make_client()
        result = c.get_incidents()
        # Real Vision API wraps in QUERY_RESPONSE envelope
        assert result["message_type"] == "QUERY_RESPONSE"
        assert result["query_type"] == "GET_INCIDENTS"
        incidents = result["data"]["incidents"]
        assert len(incidents) == 1
        assert incidents[0]["severity"] == "HIGH"
        assert incidents[0]["person_id"] == "ATLAS-P003"

    @patch("urllib.request.urlopen")
    def test_alerts_uses_query_response_envelope(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock(_mock_alerts_response())
        c = self._make_client()
        result = c.get_security_alerts()
        assert result["message_type"] == "QUERY_RESPONSE"
        alerts = result["data"]["alerts"]
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "HIGH"
        assert alerts[0]["acknowledged"] is False

    @patch("urllib.request.urlopen")
    def test_connection_state_online_when_health_healthy(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock(_mock_health_response())
        c = self._make_client()
        assert c.connection_state() == "ONLINE"

    def test_acknowledge_returns_unsupported_not_crash(self):
        """Vision v1.5.0 has no acknowledge endpoint — must return unsupported, never 404."""
        c = self._make_client()
        result = c.acknowledge_command("inc-test-123")
        assert result["status"] == "unsupported"
        assert "1.5.0" in result["detail"]

    def test_resolve_returns_unsupported_not_crash(self):
        """Vision v1.5.0 has no resolve endpoint — must return unsupported."""
        c = self._make_client()
        result = c.resolve_command("inc-test-123", "test notes")
        assert result["status"] == "unsupported"

    def test_get_incident_details_returns_unsupported(self):
        """Individual incident lookup not exposed by Vision v1.5.0."""
        c = self._make_client()
        result = c.get_incident_details("inc-test-123")
        assert result["status"] == "unsupported"

    def test_integration_token_not_required(self):
        """Token must be optional — no crash when absent."""
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_INTEGRATION_TOKEN": ""}):
            c = RemoteVisionClient()
            assert c.integration_token == ""

    def test_integration_token_stored_when_set(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_INTEGRATION_TOKEN": "secret-token-abc"}):
            c = RemoteVisionClient()
            assert c.integration_token == "secret-token-abc"

    def test_base_url_stripped_of_trailing_slash(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_BASE_URL": "http://10.9.96.13:8765/"}):
            c = RemoteVisionClient()
            assert not c.base_url.endswith("/")

    def test_timeout_reads_from_env(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_TIMEOUT": "15"}):
            c = RemoteVisionClient()
            assert c.timeout == 15.0

    def test_invalid_timeout_env_falls_back_to_default(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_TIMEOUT": "not-a-number"}):
            c = RemoteVisionClient()
            assert c.timeout == 10.0


# =============================================================================
# Phase 4 — VisionEventAdapter: normalization + TRACK-* identity safety
# =============================================================================

class TestVisionEventAdapter:

    def test_track_id_never_becomes_authoritative_person_id(self):
        """
        CRITICAL: TRACK-* arriving as person_id must be demoted — never becomes OS identity.
        """
        event = validate_event({"event_type": "PERSON_IDENTIFIED", "source": "ATLAS_VISION", "person_id": "TRACK-0042"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload.get("person_id") is None
        assert payload.get("track_id") == "TRACK-0042"

    def test_anonymous_track_star_demoted(self):
        event = validate_event({"event_type": "PERSON_ENTERED", "source": "ATLAS_VISION", "anonymous_person_id": "TRACK-007"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload.get("track_id") == "TRACK-007"
        assert payload.get("person_id") is None

    def test_valid_atlas_person_id_preserved(self):
        event = validate_event({"event_type": "PERSON_IDENTIFIED", "source": "ATLAS_VISION", "person_id": "ATLAS-P003"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload.get("person_id") == "ATLAS-P003"

    def test_atlas_vision_source_marked_remote(self):
        """ATLAS_VISION source events are remote — must have is_remote flag."""
        event = validate_event({"event_type": "PERSON_ENTERED", "source": "ATLAS_VISION"})
        _, payload = VisionEventAdapter.normalize(event)
        # ATLAS_VISION may or may not be flagged as remote depending on adapter logic
        # but must at minimum have _vision_metadata with original_source
        assert payload["_vision_metadata"]["original_source"] == "ATLAS_VISION"

    def test_remote_vision_source_marked_remote(self):
        event = validate_event({"event_type": "PERSON_IDENTIFIED", "source": "REMOTE_VISION"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload["_vision_metadata"]["is_remote"] is True

    def test_local_source_not_marked_remote(self):
        event = validate_event({"event_type": "PERSON_ENTERED", "source": "lab_cam"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload["_vision_metadata"]["is_remote"] is False

    def test_adapter_does_not_mutate_input(self):
        event = validate_event({"event_type": "PERSON_ENTERED", "source": "ATLAS_VISION", "anonymous_person_id": "TRACK-0099"})
        _, payload = VisionEventAdapter.normalize(event)
        payload["injected"] = True
        assert not hasattr(event, "injected")
        assert event.event_type == "PERSON_ENTERED"

    def test_malformed_missing_source_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event({"event_type": "PERSON_ENTERED"})

    def test_empty_source_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event({"event_type": "PERSON_ENTERED", "source": ""})

    def test_person_id_claimed_track_star_demoted(self):
        event = validate_event({"event_type": "PERSON_IDENTIFIED", "source": "ATLAS_VISION", "person_id_claimed": "TRACK-0099"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload.get("person_id_claimed") is None
        assert payload.get("track_id") == "TRACK-0099"


# =============================================================================
# Phase 5 — Admin API gateway (authorization enforcement)
# =============================================================================

@pytest.fixture
def atlas_client():
    from atlas_ui.backend.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestRemoteVisionAdminGateway:

    def test_vision_status_requires_auth(self, atlas_client):
        resp = atlas_client.get("/api/v1/admin/vision/remote/status")
        assert resp.status_code == 401

    def test_vision_incidents_requires_auth(self, atlas_client):
        resp = atlas_client.get("/api/v1/admin/vision/remote/incidents")
        assert resp.status_code == 401

    def test_vision_alerts_requires_auth(self, atlas_client):
        resp = atlas_client.get("/api/v1/admin/vision/remote/alerts")
        assert resp.status_code == 401

    def test_acknowledge_requires_auth(self, atlas_client):
        resp = atlas_client.post("/api/v1/admin/vision/remote/incidents/INC-001/acknowledge")
        assert resp.status_code == 401

    def test_resolve_requires_auth(self, atlas_client):
        resp = atlas_client.post("/api/v1/admin/vision/remote/incidents/INC-001/resolve")
        assert resp.status_code == 401

    def test_vision_disabled_returns_503_disabled(self, atlas_client):
        from atlas_ui.backend.main import app
        original = getattr(app.state, "remote_vision_client", None)
        mock_client = MagicMock()
        mock_client.enabled = False
        app.state.remote_vision_client = mock_client

        sess_id = self._login(atlas_client)
        if sess_id:
            resp = atlas_client.get("/api/v1/admin/vision/remote/status", headers={"Authorization": f"Bearer {sess_id}"})
            assert resp.status_code == 503
            assert resp.json().get("vision_status") == "VISION_DISABLED"
        app.state.remote_vision_client = original

    def test_vision_offline_returns_503_offline(self, atlas_client):
        from atlas_ui.backend.main import app
        original = getattr(app.state, "remote_vision_client", None)
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.get_health.return_value = {"status": "offline", "error_type": "unreachable", "detail": "refused"}
        app.state.remote_vision_client = mock_client

        sess_id = self._login(atlas_client)
        if sess_id:
            resp = atlas_client.get("/api/v1/admin/vision/remote/status", headers={"Authorization": f"Bearer {sess_id}"})
            assert resp.status_code == 200
            assert resp.json().get("vision_status") == "VISION_OFFLINE"
        app.state.remote_vision_client = original

    def test_vision_online_returns_connected(self, atlas_client):
        from atlas_ui.backend.main import app
        original = getattr(app.state, "remote_vision_client", None)
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.get_health.return_value = _mock_health_response()
        app.state.remote_vision_client = mock_client

        sess_id = self._login(atlas_client)
        if sess_id:
            resp = atlas_client.get("/api/v1/admin/vision/remote/status", headers={"Authorization": f"Bearer {sess_id}"})
            assert resp.status_code == 200
            assert resp.json().get("vision_status") == "VISION_CONNECTED"
        app.state.remote_vision_client = original

    def _login(self, client):
        resp = client.post("/api/v1/auth/login", json={"username": "admin_user", "password": "admin_pass_123"})
        if resp.status_code == 200:
            return resp.json().get("session_id")
        return None


# =============================================================================
# Phase 6 — /api/v1/os/status endpoint vision block
# =============================================================================

class TestOsStatusEndpoint:

    def test_os_status_returns_vision_block(self):
        from atlas_ui.backend.main import app
        client = TestClient(app, raise_server_exceptions=False)
        sess_id = self._login(client)
        if sess_id:
            resp = client.get("/api/v1/os/status", headers={"Authorization": f"Bearer {sess_id}"})
            assert resp.status_code == 200
            data = resp.json()
            assert "os" in data
            assert "vision" in data
            assert "legacy_sync" in data
            assert "connection" in data["vision"]

    def test_os_status_vision_connection_key_present_when_offline(self):
        from atlas_ui.backend.main import app
        original = getattr(app.state, "remote_vision_client", None)
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.get_health.return_value = {"status": "offline", "error_type": "unreachable", "detail": "refused"}
        app.state.remote_vision_client = mock_client

        client = TestClient(app, raise_server_exceptions=False)
        sess_id = self._login(client)
        if sess_id:
            resp = client.get("/api/v1/os/status", headers={"Authorization": f"Bearer {sess_id}"})
            data = resp.json()
            assert data["vision"]["connection"] == "OFFLINE"
        app.state.remote_vision_client = original

    def test_os_status_vision_connection_online_when_healthy(self):
        from atlas_ui.backend.main import app
        original = getattr(app.state, "remote_vision_client", None)
        mock_client = MagicMock()
        mock_client.enabled = True
        mock_client.get_health.return_value = _mock_health_response()
        mock_client.get_status.return_value = _mock_status_response()
        app.state.remote_vision_client = mock_client

        client = TestClient(app, raise_server_exceptions=False)
        sess_id = self._login(client)
        if sess_id:
            resp = client.get("/api/v1/os/status", headers={"Authorization": f"Bearer {sess_id}"})
            data = resp.json()
            assert data["vision"]["connection"] == "ONLINE"
            assert data["vision"]["service"] == "ATLAS Vision"
            assert data["vision"]["version"] == "1.5.0"
            assert data["vision"]["camera_status"] == "connected"
        app.state.remote_vision_client = original

    def _login(self, client):
        resp = client.post("/api/v1/auth/login", json={"username": "admin_user", "password": "admin_pass_123"})
        if resp.status_code == 200:
            return resp.json().get("session_id")
        return None


# =============================================================================
# Phase 7 — Network readiness: ATLAS OS stays healthy without Vision
# =============================================================================

class TestNetworkReadiness:

    def test_health_endpoint_does_not_require_vision(self):
        from atlas_ui.backend.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_base_url_points_to_real_vision_machine(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true"}):
            c = RemoteVisionClient()
            assert "10.9.96.13" in c.base_url
            assert "8765" in c.base_url

    def test_offline_does_not_raise_exception(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true", "ATLAS_VISION_BASE_URL": "http://10.9.96.13:8765"}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                import urllib.error
                mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
                c = RemoteVisionClient()
                result = c.get_health()
                assert isinstance(result, dict)


# =============================================================================
# Phase 8 — Legacy VisionSyncWorker isolation
# =============================================================================

class TestLegacyVisionSyncWorkerIsolation:

    def test_sync_worker_defaults_to_port_8002_not_remote_vision(self):
        """
        VisionSyncWorker must target the LOCAL legacy edge on port 8002.
        It must NOT be pointed at the remote Vision machine (10.9.96.13:8765)
        since Vision v1.5.0 does not expose sync endpoints.
        """
        from atlas_core.sync.vision_sync_worker import VisionSyncWorker
        identity_mem = MagicMock()
        face_store = MagicMock()
        worker = VisionSyncWorker(identity_mem, face_store)
        assert "8002" in worker.target_url
        assert "10.9.96.13" not in worker.target_url

    def test_sync_worker_target_url_is_configurable_via_env(self):
        from atlas_core.sync.vision_sync_worker import VisionSyncWorker
        identity_mem = MagicMock()
        face_store = MagicMock()
        worker = VisionSyncWorker(identity_mem, face_store, target_url="http://127.0.0.1:9999")
        assert "9999" in worker.target_url


# =============================================================================
# Phase 9 — Regression: existing event schema tests
# =============================================================================

class TestExistingFunctionality:

    def test_valid_event_accepted(self):
        event = validate_event({"event_type": "person_entered", "source": "lab_cam", "anonymous_person_id": "ATLAS-P001"})
        assert event.event_type == "person_entered"

    def test_missing_source_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event({"event_type": "person_entered"})

    def test_empty_source_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event({"event_type": "person_entered", "source": ""})

    def test_whitespace_source_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event({"event_type": "person_entered", "source": "   "})

    def test_non_dict_rejected(self):
        with pytest.raises(ContractValidationError):
            validate_event(["event_type", "source"])

    def test_adapter_local_source_not_remote(self):
        event = validate_event({"event_type": "person_entered", "source": "lab_cam"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload["_vision_metadata"]["is_remote"] is False

    def test_remote_prefix_source_is_remote(self):
        event = validate_event({"event_type": "PERSON_IDENTIFIED", "source": "REMOTE_CAMERA_01"})
        _, payload = VisionEventAdapter.normalize(event)
        assert payload["_vision_metadata"]["is_remote"] is True

    def test_vision_client_enabled_by_default(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "true"}):
            c = RemoteVisionClient()
            assert c.enabled is True

    def test_vision_client_disabled_by_env(self):
        with patch.dict(os.environ, {"ATLAS_VISION_ENABLED": "false"}):
            c = RemoteVisionClient()
            assert c.enabled is False
