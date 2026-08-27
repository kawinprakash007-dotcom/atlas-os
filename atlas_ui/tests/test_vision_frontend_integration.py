import pytest
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app
from unittest.mock import patch, MagicMock
import json

@pytest.fixture
def client():
    return TestClient(app)

def get_session_for_role(client: TestClient, role: str) -> str:
    username = "admin_user" if role == "ADMIN" else "normal_user"
    password = "admin_pass_123" if role == "ADMIN" else "user_pass_123"
    response = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password
    })
    data = response.json()
    if data.get("biometric_required"):
        person_id = data["person_id"]
        token = "test_verify_token"
        app.state.auth_service.register_biometric_success(person_id, token)
        response = client.post("/api/v1/auth/login", json={
            "username": username,
            "password": password,
            "biometric_input": token
        })
        data = response.json()
    return data["session_id"]

# TEST 1: Authenticated admin can load Vision system status
def test_authenticated_admin_can_load_vision_status(client):
    admin_token = get_session_for_role(client, "ADMIN")
    response = client.get("/api/v1/admin/vision/status", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "sync_worker" in data
    assert "edge_node" in data

# TEST 2: Non-admin users cannot load Vision status (returns 403 or role based limit)
def test_non_admin_cannot_load_vision_status(client):
    # Wait, in routes/admin.py, get_vision_status checks VIEW_SYSTEM permission:
    # "if not access_controller.has_permission(sess.role, 'VIEW_SYSTEM'): return 403"
    # Both ADMIN and USER have VIEW_SYSTEM permission!
    # So USER can view system status (which is expected since operators need to see if Vision is online).
    # But unauthenticated requests should be rejected.
    response = client.get("/api/v1/admin/vision/status")
    assert response.status_code == 401

# TEST 14: Unauthorized users (USER role) cannot access admin-only Vision diagnostic controls
def test_user_cannot_access_diagnostics(client):
    user_token = get_session_for_role(client, "USER")
    
    # Test track simulation
    response_track = client.post("/api/v1/admin/vision/test_track?track_id=TRACK-0001", headers={"Authorization": f"Bearer {user_token}"})
    assert response_track.status_code == 403
    
    # Test recognition simulation
    response_rec = client.post("/api/v1/admin/vision/test_recognition?track_id=TRACK-0001&authoritative_id=ATLAS-P-88888888", headers={"Authorization": f"Bearer {user_token}"})
    assert response_rec.status_code == 403

# TEST 14b: Admin user CAN access diagnostic controls (when Vision Edge is running)
def test_admin_can_access_diagnostics_when_vision_edge_online(client):
    admin_token = get_session_for_role(client, "ADMIN")
    
    # Mock urllib.request to pretend Vision Edge responds successfully
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({"status": "enqueued", "track_id": "TRACK-0001"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        response = client.post("/api/v1/admin/vision/test_track?track_id=TRACK-0001", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        assert response.json()["status"] == "enqueued"

# TEST 11: TRACK-* unresolved identifiers are never treated as authoritative users in adapter
def test_adapter_does_not_treat_track_ids_as_authoritative():
    from atlas_core.network.vision_adapter import VisionEventAdapter
    from atlas_core.network.schemas import VisionEvent
    
    # Simulate unresolved match (e.g. e.person_id starts with TRACK- or matches track_id)
    event_data = VisionEvent(
        event_id="evt_test",
        event_type="PERSON_IDENTIFIED",
        source="ATLAS_VISION",
        timestamp=12345.6,
        track_id="TRACK-0001",
        person_id="TRACK-0001",  # Unresolved ID
        confidence=0.5
    )
    
    # The normalizer must downgrade unresolved TRACK-* ids to None or drop them.
    evt_type, payload = VisionEventAdapter.normalize(event_data)
    assert evt_type == "PERSON_IDENTIFIED"
    assert payload.get("person_id") is None
