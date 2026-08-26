import os

class UIConfiguration:
    def __init__(
        self,
        session_lifetime_seconds: float = 3600.0,
        face_camera_index: int = 0,
        face_match_threshold: float = 0.75,
        face_enrollment_samples: int = 5,
        face_capture_timeout: float = 5.0
    ):
        self.session_lifetime_seconds = session_lifetime_seconds
        self.face_camera_index = face_camera_index
        self.face_match_threshold = face_match_threshold
        self.face_enrollment_samples = face_enrollment_samples
        self.face_capture_timeout = face_capture_timeout

        # Centralize absolute biometric storage path relative to configuration directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.biometrics_store_path = os.path.abspath(os.path.join(current_dir, "data", "biometrics.json"))

