import sys
import cv2
import numpy as np
from typing import Optional

class CameraManager:
    """
    Manages cv2.VideoCapture lifecycle and handles cross-platform backend settings.
    Prefer cv2.CAP_DSHOW on Windows with fallback to default backend.
    """
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None

    def open_camera(self) -> cv2.VideoCapture:
        """
        Opens the camera stream with DirectShow on Windows, falling back to default if needed.
        Performs frame validation to guarantee camera usability.
        """
        if self.cap is not None:
            return self.cap

        is_windows = sys.platform.startswith("win")
        
        if is_windows:
            print(f"[CAMERA] Attempting to open camera index {self.camera_index} with cv2.CAP_DSHOW...", flush=True)
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            
            # Validate CAP_DSHOW by attempting to read a frame
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    print(f"[CAMERA] DirectShow opened successfully on index {self.camera_index}.", flush=True)
                    self.cap = cap
                    return self.cap
                else:
                    print(f"[CAMERA] DirectShow opened but failed frame validation. Releasing and trying fallback.", flush=True)
                    cap.release()
        
        # Fallback to default backend
        print(f"[CAMERA] Attempting to open camera index {self.camera_index} with default backend...", flush=True)
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"Camera source index {self.camera_index} could not be initialized.")

        # Validate captured frame
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            cap.release()
            raise RuntimeError(f"Camera index {self.camera_index} opened but no frames could be captured.")

        print(f"[CAMERA] Camera index {self.camera_index} opened successfully with default backend.", flush=True)
        self.cap = cap
        return self.cap

    def open(self) -> bool:
        """
        Alias for open_camera() that returns True on success,
        or raises a controlled RuntimeError on failure.
        """
        try:
            self.open_camera()
            return True
        except RuntimeError:
            return False

    def flush_frames(self, count: int = 5) -> None:
        """
        Reads and discards 'count' frames to drain the hardware buffer.

        OpenCV's VideoCapture maintains an internal ring buffer. On re-open the first
        several frames may be stale frames from the previous session. This method
        must be called after open_camera() to guarantee fresh frames.
        """
        if self.cap is None:
            return
        for _ in range(count):
            self.cap.read()

    def capture_frame(self) -> np.ndarray:
        """
        Captures a single fresh frame from the opened camera.
        """
        if self.cap is None:
            raise RuntimeError("Camera is not opened. Call open_camera() first or use as a context manager.")
        
        ret, frame = self.cap.read()
        if not ret or frame is None or frame.size == 0:
            raise RuntimeError("Failed to capture frame from camera stream.")
        
        return frame

    def read(self) -> np.ndarray:
        """
        Alias for capture_frame().
        """
        return self.capture_frame()

    def release(self) -> None:
        """
        Releases the VideoCapture resources.
        """
        if self.cap is not None:
            print(f"[CAMERA] Releasing camera index {self.camera_index}...", flush=True)
            self.cap.release()
            self.cap = None

    def __enter__(self) -> "CameraManager":
        self.open_camera()
        # Always flush stale buffered frames on every open
        self.flush_frames(count=5)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
