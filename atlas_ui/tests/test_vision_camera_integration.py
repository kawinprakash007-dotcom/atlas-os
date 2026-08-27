import pytest
import os
import cv2
import json
import time
import numpy as np
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from atlas_ui.backend.main import app
from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_core.network.vision_adapter import VisionEventAdapter
from atlas_core.network.schemas import VisionEvent

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

# Mock VideoCapture & YOLOFaceDetector fixture
@pytest.fixture
def mock_video_capture():
    with patch("cv2.VideoCapture") as mock_cap_class, \
         patch("atlas_ui.backend.vision.camera_manager.YOLOFaceDetector") as mock_yolo_class:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        
        # Mock frame return: (True, 480x640 BGR frame)
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, mock_frame)
        
        mock_cap_class.return_value = mock_cap
        
        mock_yolo = MagicMock()
        mock_yolo.detect.return_value = MagicMock(faces=[])
        mock_yolo_class.return_value = mock_yolo
        
        yield mock_cap

# TEST 1: CameraManager creation and initialization
def test_camera_manager_creation(mock_video_capture):
    cm = CameraManager()
    assert cm.camera_enabled is True
    assert cm.is_connected is False
    assert cm.latest_frame is None

# TEST 2: Camera disabled mode
def test_camera_disabled_mode(mock_video_capture):
    with patch.dict(os.environ, {"ATLAS_CAMERA_ENABLED": "false"}):
        cm = CameraManager()
        assert cm.camera_enabled is False
        started = cm.start()
        assert started is False

# TEST 3: Failed camera source handling
def test_failed_camera_source_handling():
    with patch("cv2.VideoCapture") as mock_cap_class:
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cap_class.return_value = mock_cap
        
        cm = CameraManager()
        # Mock thread loop run to disconnect immediately on false
        cm.camera_fps = 1000  # fast loop
        cm.start()
        time.sleep(0.1)
        cm.stop()
        assert cm.is_connected is False

# TEST 4 & 5: Start does not duplicate loop and Stop releases cleanly
def test_camera_start_stop_idempotency(mock_video_capture):
    cm = CameraManager()
    assert cm.start() is True
    # Second start returns True immediately
    assert cm.start() is True
    
    time.sleep(0.1)
    assert cm._thread.is_alive() is True
    cm.stop()
    assert cm._thread is None

# TEST 6: Vision camera status endpoint
def test_vision_camera_status_endpoint(client):
    admin_token = get_session_for_role(client, "ADMIN")
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = json.dumps({
            "status": "connected",
            "source": "0",
            "camera_enabled": True,
            "fps": 20.0,
            "width": 1280,
            "height": 720,
            "frames_received": 100,
            "frames_processed": 50,
            "active_tracks": 0,
            "reconnect_count": 0,
            "last_frame_timestamp": 123456.78,
            "error": None
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        response = client.get("/api/v1/admin/vision/camera/status", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"

# TEST 7: Camera unavailable returns graceful response
def test_camera_frame_unavailable_returns_503(client):
    admin_token = get_session_for_role(client, "ADMIN")
    from urllib.error import HTTPError
    import io
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url="http://127.0.0.1:8002/api/v1/vision/camera/frame",
            code=503,
            msg="Camera frame unavailable",
            hdrs=None,
            fp=io.BytesIO(b"Camera frame unavailable")
        )
        response = client.get("/api/v1/admin/vision/camera/frame", headers={"Authorization": f"Bearer {admin_token}"})
        assert response.status_code == 503

# TEST 8 & 9: OS Gateway Authorization and unauthorized control blocking
def test_unauthorized_camera_control(client):
    user_token = get_session_for_role(client, "USER")
    
    # Start request
    response_start = client.post("/api/v1/admin/vision/camera/start", headers={"Authorization": f"Bearer {user_token}"})
    assert response_start.status_code == 403
    
    # Stop request
    response_stop = client.post("/api/v1/admin/vision/camera/stop", headers={"Authorization": f"Bearer {user_token}"})
    assert response_stop.status_code == 403

# TEST 11: TRACK-* IDs never become authoritative identities
def test_track_id_safety_invariant():
    event_data = VisionEvent(
        event_id="evt_test",
        event_type="PERSON_IDENTIFIED",
        source="ATLAS_VISION",
        timestamp=12345.6,
        track_id="TRACK-0001",
        person_id="TRACK-0001",  # Malicious/unresolved track ID
        confidence=0.9
    )
    # Adapter must strip it
    evt_type, payload = VisionEventAdapter.normalize(event_data)
    assert payload.get("person_id") is None
