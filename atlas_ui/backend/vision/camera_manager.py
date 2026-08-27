import os
import cv2
import sys
import time
import queue
import threading
import numpy as np
from typing import Optional, Dict, Tuple, Any

from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.event_dispatcher import VisionEventDispatcher
from atlas_ui.backend.vision.biometrics_manager import BiometricBindingManager
from atlas_ui.backend.vision.recognition_worker import RecognitionWorker

class FaceTracker:
    def __init__(self, dist_threshold=100.0, max_unseen_seconds=3.0):
        self.dist_threshold = dist_threshold
        self.max_unseen_seconds = max_unseen_seconds
        self.tracks = {}  # track_id -> { "centroid": (cx, cy), "bbox": [x1, y1, x2, y2], "last_seen": timestamp }
        self.counter = 0

    def update(self, detected_bboxes):
        now = time.time()
        new_tracks = {}
        
        # Calculate centroids of detected bboxes
        detected_centroids = []
        for bbox in detected_bboxes:
            x1, y1, x2, y2 = bbox
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            detected_centroids.append(((cx, cy), bbox))

        # Match with existing active tracks
        matched_detections = set()
        for track_id, info in self.tracks.items():
            if now - info["last_seen"] > self.max_unseen_seconds:
                continue # drop stale track
                
            tc = info["centroid"]
            best_idx = None
            best_dist = float('inf')
            
            for i, (dc, dbbox) in enumerate(detected_centroids):
                if i in matched_detections:
                    continue
                dist = np.sqrt((tc[0] - dc[0])**2 + (tc[1] - dc[1])**2)
                if dist < best_dist and dist < self.dist_threshold:
                    best_dist = dist
                    best_idx = i
            
            if best_idx is not None:
                new_tracks[track_id] = {
                    "centroid": detected_centroids[best_idx][0],
                    "bbox": detected_centroids[best_idx][1],
                    "last_seen": now
                }
                matched_detections.add(best_idx)
            else:
                # Keep active track for a bit if unseen
                new_tracks[track_id] = info

        # Create new tracks for unmatched detections
        for i, (dc, dbbox) in enumerate(detected_centroids):
            if i in matched_detections:
                continue
            self.counter += 1
            track_id = f"TRACK-{self.counter:04d}"
            new_tracks[track_id] = {
                "centroid": dc,
                "bbox": dbbox,
                "last_seen": now
            }
            # Yield new track entry event
            yield "PERSON_ENTERED", track_id, dbbox

        self.tracks = new_tracks

class CameraManager:
    """
    Manages cv2.VideoCapture lifecycle supporting both background capture thread mode
    (started via start()) and synchronous fallback mode (called via open_camera()/capture_frame() directly).
    """
    def __init__(
        self,
        camera_index: Optional[Any] = None,
        event_dispatcher: Optional[VisionEventDispatcher] = None,
        binding_manager: Optional[BiometricBindingManager] = None,
        recognition_worker: Optional[RecognitionWorker] = None
    ):
        self.event_dispatcher = event_dispatcher
        self.binding_manager = binding_manager
        self.recognition_worker = recognition_worker

        # Load environment configuration
        self.camera_enabled = os.environ.get("ATLAS_CAMERA_ENABLED", "true").lower() == "true"
        
        # Backwards compatibility: if camera_index is passed directly, prioritize it.
        if camera_index is not None:
            self.camera_source = camera_index
        else:
            self.source_raw = os.environ.get("ATLAS_CAMERA_SOURCE", "0")
            try:
                self.camera_source = int(self.source_raw)
            except ValueError:
                self.camera_source = self.source_raw  # Keep as URL/string

        self.camera_fps = int(os.environ.get("ATLAS_CAMERA_FPS", "20"))
        self.width = int(os.environ.get("ATLAS_CAMERA_WIDTH", "1280"))
        self.height = int(os.environ.get("ATLAS_CAMERA_HEIGHT", "720"))
        self.detection_fps = int(os.environ.get("ATLAS_DETECTION_FPS", "10"))
        self.rec_cooldown = float(os.environ.get("ATLAS_RECOGNITION_COOLDOWN_SECONDS", "3.0"))

        # Threads and Synchronization
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.cap: Optional[cv2.VideoCapture] = None

        # Telemetry State
        self.is_connected = False
        self.current_fps = 0.0
        self.frames_received = 0
        self.frames_processed = 0
        self.reconnect_count = 0
        self.last_frame_timestamp: Optional[float] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.error_message: Optional[str] = None
        self.dropped_rec_tasks = 0

        # Tracker
        self.tracker = FaceTracker()
        self.last_rec_enqueue: Dict[str, float] = {}  # track_id -> timestamp
        self.detector: Optional[YOLOFaceDetector] = None

    def start(self) -> bool:
        """
        Starts the background camera capture thread.
        """
        if not self.camera_enabled:
            print("[CameraManager] Camera is disabled via configuration.")
            return False

        with self._lock:
            if self._thread and self._thread.is_alive():
                print("[CameraManager] Capture loop is already running.")
                return True

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._capture_loop, name="ATLAS_Camera_Capture", daemon=True)
            self._thread.start()
            print("[CameraManager] Starting camera capture thread...")
            return True

    def stop(self):
        """
        Gracefully stops the camera capture thread and releases cv2 resources.
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None
        self._release_video_capture()
        print("[CameraManager] Stopped camera capture cleanly.")

    def open_camera(self) -> cv2.VideoCapture:
        """
        Backwards-compatible open method. If background loop is running, waits for it.
        Otherwise, opens the camera synchronously.
        """
        if self._thread and self._thread.is_alive():
            start_wait = time.time()
            while not self.is_connected and time.time() - start_wait < 2.0:
                time.sleep(0.05)
            if not self.is_connected:
                raise RuntimeError(f"Camera source {self.camera_source} could not be initialized.")
            return self.cap

        # Synchronous mode open
        if self.cap is not None:
            return self.cap

        is_windows = sys.platform.startswith("win")
        try:
            if is_windows and isinstance(self.camera_source, int):
                try:
                    cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                except Exception:
                    cap = cv2.VideoCapture(self.camera_source)
            else:
                cap = cv2.VideoCapture(self.camera_source)
        except Exception as e:
            raise RuntimeError(f"Camera source {self.camera_source} could not be initialized: {e}")

        if not cap.isOpened():
            raise RuntimeError(f"Camera source {self.camera_source} could not be initialized.")

        # Validate captured frame
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            cap.release()
            raise RuntimeError(f"Camera source {self.camera_source} opened but no frames could be captured.")

        self.cap = cap
        self.is_connected = True
        with self._lock:
            self.latest_frame = frame.copy()
            self.last_frame_timestamp = time.time()
        return self.cap

    def open(self) -> bool:
        try:
            self.open_camera()
            return True
        except RuntimeError:
            return False

    def flush_frames(self, count: int = 5):
        if self.cap is not None:
            for _ in range(count):
                self.cap.read()

    def capture_frame(self) -> np.ndarray:
        if self._thread and self._thread.is_alive():
            frame = self.get_latest_frame()
            if frame is None:
                raise RuntimeError("Failed to capture frame from camera stream.")
            return frame

        # Synchronous read
        if self.cap is None:
            raise RuntimeError("Camera is not opened. Call open_camera() first or use as a context manager.")
        ret, frame = self.cap.read()
        if not ret or frame is None or frame.size == 0:
            raise RuntimeError("Failed to capture frame from camera stream.")
        with self._lock:
            self.latest_frame = frame.copy()
            self.last_frame_timestamp = time.time()
        return frame

    def read(self) -> np.ndarray:
        return self.capture_frame()

    def release(self):
        self.stop()

    def __enter__(self) -> "CameraManager":
        self.open_camera()
        self.flush_frames(count=5)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        Thread-safe read of the latest frame.
        """
        with self._lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None

    def get_status(self) -> Dict[str, Any]:
        """
        Returns runtime stats.
        """
        with self._lock:
            active_tracks = list(self.tracker.tracks.keys())
            return {
                "status": "connected" if self.is_connected else "disconnected",
                "source": str(self.camera_source),
                "camera_enabled": self.camera_enabled,
                "fps": round(self.current_fps, 1),
                "width": self.width,
                "height": self.height,
                "frames_received": self.frames_received,
                "frames_processed": self.frames_processed,
                "active_tracks": len(active_tracks),
                "reconnect_count": self.reconnect_count,
                "last_frame_timestamp": self.last_frame_timestamp,
                "error": self.error_message,
                "dropped_rec_tasks": self.dropped_rec_tasks
            }

    def _release_video_capture(self):
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.is_connected = False

    def _capture_loop(self):
        print(f"[CameraManager] Capture loop started. Source: {self.camera_source}")
        
        try:
            self.detector = YOLOFaceDetector()
        except Exception as e:
            print(f"[CameraManager] Error loading YOLOFaceDetector: {e}")
            self.error_message = f"Model load failure: {e}"
            return

        reconnect_delay = 1.0
        max_reconnect_delay = 16.0
        frame_interval = 1.0 / self.camera_fps
        detection_interval = 1.0 / self.detection_fps

        last_detection_time = 0.0
        fps_start_time = time.time()
        fps_frame_count = 0

        while not self._stop_event.is_set():
            if self.cap is None or not self.cap.isOpened():
                self._release_video_capture()
                print(f"[CameraManager] Connecting to camera source: {self.camera_source}...")
                
                try:
                    is_windows = sys.platform.startswith("win")
                    if is_windows and isinstance(self.camera_source, int):
                        try:
                            self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                        except Exception as e:
                            print(f"[CameraManager] CAP_DSHOW failed: {e}. Trying default backend...")
                            self.cap = cv2.VideoCapture(self.camera_source)
                    else:
                        self.cap = cv2.VideoCapture(self.camera_source)
                except Exception as e:
                    self.cap = None
                    print(f"[CameraManager] Exception opening VideoCapture: {e}")

                if self.cap.isOpened():
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    
                    ret, test_frame = self.cap.read()
                    if ret and test_frame is not None and test_frame.size > 0:
                        print("[CameraManager] Camera connected and verified.")
                        self.is_connected = True
                        self.error_message = None
                        reconnect_delay = 1.0
                    else:
                        print("[CameraManager] Connected but frame validation failed.")
                        self._release_video_capture()
                
                if not self.is_connected:
                    self.reconnect_count += 1
                    self.error_message = "Camera offline / failed frame verification"
                    print(f"[CameraManager] Reconnect failed. Retrying in {reconnect_delay}s...")
                    self._stop_event.wait(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue

            loop_start = time.time()
            ret, frame = self.cap.read()
            if not ret or frame is None or frame.size == 0:
                print("[CameraManager] Failed to read frame. Socking connection...")
                self._release_video_capture()
                continue

            self.frames_received += 1
            now = time.time()
            with self._lock:
                self.latest_frame = frame.copy()
                self.last_frame_timestamp = now

            fps_frame_count += 1
            if now - fps_start_time >= 2.0:
                self.current_fps = fps_frame_count / (now - fps_start_time)
                fps_frame_count = 0
                fps_start_time = now

            if now - last_detection_time >= detection_interval:
                last_detection_time = now
                self.frames_processed += 1

                if self.detector:
                    det_result = self.detector.detect(frame)
                    detected_bboxes = [face.bbox for face in det_result.faces]
                    
                    new_track_events = list(self.tracker.update(detected_bboxes))
                    for event_type, track_id, bbox in new_track_events:
                        print(f"[CameraManager] Event: {event_type} | {track_id}")
                        if self.event_dispatcher:
                            self.event_dispatcher.dispatch(
                                event_type,
                                {"track_id": track_id, "source": "ATLAS_VISION"}
                            )

                    for track_id, track_info in self.tracker.tracks.items():
                        is_bound = self.binding_manager.resolve(track_id) if self.binding_manager else None
                        if not is_bound:
                            last_enq = self.last_rec_enqueue.get(track_id, 0.0)
                            if now - last_enq >= self.rec_cooldown:
                                self.last_rec_enqueue[track_id] = now
                                if self.recognition_worker:
                                    success = self.recognition_worker.enqueue(track_id, frame, track_info["bbox"])
                                    if not success:
                                        self.dropped_rec_tasks += 1

            elapsed = time.time() - loop_start
            sleep_time = max(0.001, frame_interval - elapsed)
            self._stop_event.wait(sleep_time)
            
        self._release_video_capture()
        print("[CameraManager] Capture thread exiting.")
