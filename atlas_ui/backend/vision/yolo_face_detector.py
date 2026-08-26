import os
import urllib.request
import numpy as np
from typing import Optional, List
from ultralytics import YOLO

from atlas_ui.backend.vision.face_detection_result import FaceDetection, FaceDetectionResult

# Default download URL for community pre-trained YOLOv8 face weights
YOLO_FACE_MODEL_URL = "https://huggingface.co/ElenaRyumina/MASAI_models/resolve/main/yolov8n-face.pt"

class YOLOFaceDetector:
    """
    Inference wrapper for YOLO face detection.
    Downloads weights if missing, loads weights once, and performs inference on BGR frames.
    """
    def __init__(
        self,
        model_path: Optional[str] = None,
        conf_threshold: float = 0.50,
        imgsz: int = 640
    ):
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz

        # Resolve model path relative to file directory if not specified
        if model_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(current_dir, "yolov8n-face.pt")
        
        self.model_path = model_path
        
        # Self-bootstrap download weights if missing
        self._ensure_model_exists()
        
        print(f"[YOLO] Loading face detection model from {self.model_path}...", flush=True)
        try:
            self.model = YOLO(self.model_path)
            print("[YOLO] Model loaded successfully.", flush=True)
        except Exception as e:
            raise RuntimeError(f"Failed to load YOLO model: {e}")

    def _ensure_model_exists(self) -> None:
        """
        Downloads pretrained YOLO face weights if not found locally.
        """
        if os.path.exists(self.model_path):
            print(f"[YOLO] Pre-trained weights found at: {self.model_path}", flush=True)
            return

        print(f"[YOLO] Pre-trained weights not found. Downloading from {YOLO_FACE_MODEL_URL}...", flush=True)
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            
            # Simple progress callback for download
            def report_progress(block_num, block_size, total_size):
                percent = int(block_num * block_size * 100 / total_size)
                if percent % 20 == 0:
                    print(f"[YOLO] Download progress: {min(100, percent)}%", flush=True)

            urllib.request.urlretrieve(YOLO_FACE_MODEL_URL, self.model_path, reporthook=report_progress)
            print(f"[YOLO] Download completed! Saved to {self.model_path}", flush=True)
        except Exception as e:
            # Clean up partial download if any
            if os.path.exists(self.model_path):
                os.remove(self.model_path)
            raise RuntimeError(f"Failed to download YOLO face weights from URL: {e}")

    def detect(self, frame: np.ndarray) -> FaceDetectionResult:
        """
        Performs face detection inference on a BGR image frame.
        """
        if frame is None or frame.size == 0:
            return FaceDetectionResult(faces=[], face_count=0)

        try:
            # Perform prediction
            results = self.model.predict(
                frame,
                imgsz=self.imgsz,
                conf=self.conf_threshold,
                verbose=False
            )
            
            faces: List[FaceDetection] = []
            if results and len(results) > 0:
                result = results[0]
                if result.boxes is not None:
                    for box in result.boxes:
                        # Extract bounding box float coordinates
                        xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                        # Convert to integers
                        bbox = [int(round(coord)) for coord in xyxy]
                        conf = float(box.conf[0].item())
                        
                        faces.append(FaceDetection(bbox=bbox, confidence=conf))

            return FaceDetectionResult(faces=faces, face_count=len(faces))

        except Exception as e:
            print(f"[YOLO] Inference error: {e}", flush=True)
            return FaceDetectionResult(faces=[], face_count=0)
