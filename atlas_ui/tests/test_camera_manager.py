import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from atlas_ui.backend.vision.camera_manager import CameraManager

@patch('cv2.VideoCapture')
def test_successful_open(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8))
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    assert manager.open() is True
    assert manager.cap is not None

@patch('cv2.VideoCapture')
def test_failed_open(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    assert manager.open() is False
    assert manager.cap is None

def test_read_before_open():
    manager = CameraManager(camera_index=0)
    with pytest.raises(RuntimeError, match="Camera is not opened"):
        manager.read()

@patch('cv2.VideoCapture')
def test_successful_read(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    test_frame = np.ones((480, 640, 3), dtype=np.uint8)
    mock_cap.read.return_value = (True, test_frame)
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    manager.open()
    frame = manager.read()
    assert frame is not None
    assert frame.shape == (480, 640, 3)

@patch('cv2.VideoCapture')
def test_release(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8))
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    manager.open()
    assert manager.cap is not None
    manager.release()
    assert manager.cap is None
    mock_cap.release.assert_called_once()

@patch('cv2.VideoCapture')
def test_multiple_release_calls(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8))
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    manager.open()
    manager.release()
    manager.release()  # Should not crash
    assert manager.cap is None
    mock_cap.release.assert_called_once()

@patch('cv2.VideoCapture')
def test_state_reset_after_release(mock_video_capture):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.ones((480, 640, 3), dtype=np.uint8))
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    manager.open()
    manager.release()
    
    # After release, reading should fail
    with pytest.raises(RuntimeError, match="Camera is not opened"):
        manager.read()
