import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.face_detection_result import FaceDetection, FaceDetectionResult
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector

# --- CAMERA MANAGER TESTS ---

@patch("cv2.VideoCapture")
def test_camera_manager_open_failure(mock_video_capture):
    # Mock VideoCapture to fail opening
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    with pytest.raises(RuntimeError) as excinfo:
        manager.open_camera()
    
    assert "could not be initialized" in str(excinfo.value)


@patch("cv2.VideoCapture")
def test_camera_manager_read_failure(mock_video_capture):
    # Mock VideoCapture to open but fail reading first frame (validation fail)
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (False, None)
    mock_video_capture.return_value = mock_cap

    manager = CameraManager(camera_index=0)
    with pytest.raises(RuntimeError) as excinfo:
        manager.open_camera()
    
    assert "opened but no frames could be captured" in str(excinfo.value)
    # Ensure release was called on validation failure
    mock_cap.release.assert_called()


@patch("cv2.VideoCapture")
def test_camera_manager_context_manager(mock_video_capture):
    # Mock successful open and read
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
    mock_video_capture.return_value = mock_cap

    with CameraManager(camera_index=0) as manager:
        assert manager.cap is not None
        frame = manager.capture_frame()
        assert frame.shape == (480, 640, 3)
    
    # Ensure camera was released upon exiting the block
    mock_cap.release.assert_called_once()
    assert manager.cap is None


# --- YOLO FACE DETECTOR TESTS ---

class MockBox:
    def __init__(self, xyxy, conf):
        # Mock box.xyxy[0].tolist()
        mock_xyxy = MagicMock()
        mock_xyxy[0].tolist.return_value = xyxy
        self.xyxy = mock_xyxy
        
        # Mock box.conf[0].item()
        mock_conf = MagicMock()
        mock_conf[0].item.return_value = conf
        self.conf = mock_conf


class MockResult:
    def __init__(self, boxes):
        self.boxes = boxes


@patch("os.path.exists", return_value=True)  # Mock weights file already exists locally
@patch("atlas_ui.backend.vision.yolo_face_detector.YOLO")
def test_yolo_detector_no_face(mock_yolo_class, mock_exists):
    # Setup mock YOLO predict output: 0 detections
    mock_yolo_instance = MagicMock()
    mock_yolo_instance.predict.return_value = [MockResult(boxes=[])]
    mock_yolo_class.return_value = mock_yolo_instance

    detector = YOLOFaceDetector(model_path="dummy_path.pt")
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res = detector.detect(frame)
    
    assert res.face_count == 0
    assert len(res.faces) == 0
    assert res.no_face is True
    assert res.single_face is False
    assert res.multiple_faces is False
    assert res.status == "NO_FACE"


@patch("os.path.exists", return_value=True)
@patch("atlas_ui.backend.vision.yolo_face_detector.YOLO")
def test_yolo_detector_single_face(mock_yolo_class, mock_exists):
    # Setup mock YOLO predict output: 1 detection
    mock_yolo_instance = MagicMock()
    mock_box = MockBox(xyxy=[100.0, 150.0, 200.0, 250.0], conf=0.85)
    mock_yolo_instance.predict.return_value = [MockResult(boxes=[mock_box])]
    mock_yolo_class.return_value = mock_yolo_instance

    detector = YOLOFaceDetector(model_path="dummy_path.pt")
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res = detector.detect(frame)
    
    assert res.face_count == 1
    assert len(res.faces) == 1
    assert res.faces[0].bbox == [100, 150, 200, 250]
    assert res.faces[0].confidence == 0.85
    assert res.no_face is False
    assert res.single_face is True
    assert res.multiple_faces is False
    assert res.status == "SINGLE_FACE"


@patch("os.path.exists", return_value=True)
@patch("atlas_ui.backend.vision.yolo_face_detector.YOLO")
def test_yolo_detector_multiple_faces(mock_yolo_class, mock_exists):
    # Setup mock YOLO predict output: 2 detections
    mock_yolo_instance = MagicMock()
    box1 = MockBox(xyxy=[10.0, 20.0, 30.0, 40.0], conf=0.90)
    box2 = MockBox(xyxy=[50.0, 60.0, 70.0, 80.0], conf=0.75)
    mock_yolo_instance.predict.return_value = [MockResult(boxes=[box1, box2])]
    mock_yolo_class.return_value = mock_yolo_instance

    detector = YOLOFaceDetector(model_path="dummy_path.pt")
    
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    res = detector.detect(frame)
    
    assert res.face_count == 2
    assert len(res.faces) == 2
    assert res.no_face is False
    assert res.single_face is False
    assert res.multiple_faces is True
    assert res.status == "MULTIPLE_FACES"


@patch("os.path.exists", return_value=True)
@patch("atlas_ui.backend.vision.yolo_face_detector.YOLO")
def test_yolo_detector_empty_frame_handling(mock_yolo_class, mock_exists):
    detector = YOLOFaceDetector(model_path="dummy_path.pt")
    
    # Empty frame input
    res_empty = detector.detect(None)
    assert res_empty.face_count == 0
    assert len(res_empty.faces) == 0


@patch("os.path.exists", return_value=True)
@patch("atlas_ui.backend.vision.yolo_face_detector.YOLO")
def test_yolo_detector_model_loaded_once(mock_yolo_class, mock_exists):
    detector = YOLOFaceDetector(model_path="dummy_path.pt")
    
    # Verify YOLO class constructor was called exactly once in __init__
    mock_yolo_class.assert_called_once_with("dummy_path.pt")
    
    # Run multiple predictions and verify constructor is NOT called again
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    detector.detect(frame)
    detector.detect(frame)
    mock_yolo_class.assert_called_once()

