import os
import time
import secrets
import numpy as np
from unittest.mock import patch, MagicMock

from atlas_ui.backend.configuration import UIConfiguration
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.identity.person_models import Person
from atlas_ui.backend.identity.person_registry import PersonRegistry
from atlas_ui.backend.identity.vision_identity_client import OpenCVVisionIdentityClient, FaceEnrollmentRequest
from atlas_ui.backend.identity.enrollment_service import EnrollmentService
from atlas_ui.backend.sessions.session_manager import SessionManager
from atlas_ui.backend.audit.auth_audit import AuthenticationAudit
from atlas_ui.backend.services.authentication_service import AuthenticationService
from atlas_ui.backend.biometric.face_verifier import FaceVerifier, FaceVerificationResult
from atlas_ui.backend.biometric.opencv_face_verifier import OpenCVFaceVerifier
from atlas_ui.backend.biometric.camera_manager import CameraManager
from atlas_ui.backend.biometric.face_detector import FaceDetector
from atlas_ui.backend.biometric.face_encoder import FaceEncoder
from atlas_ui.backend.biometric.face_store import FaceStore

# Mock VideoCapture class
class DummyVideoCapture:
    def __init__(self, is_opened=True, fail_read=False, num_frames=10):
        self._is_opened = is_opened
        self._fail_read = fail_read
        self._num_frames = num_frames
        self._frames_returned = 0
        self.released = False

    def isOpened(self):
        return self._is_opened

    def read(self):
        if self._fail_read or self._frames_returned >= self._num_frames:
            return False, None
        self._frames_returned += 1
        dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        return True, dummy_frame

    def release(self):
        self.released = True


def print_title(title: str):
    print("\n" + "="*80)
    print(f" {title} ")
    print("="*80)

def main():
    print("======================================================================")
    print("ATLAS OS v1.9 Real Local Biometric Pipeline Verification Demo")
    print("======================================================================")

    # Clean test file
    store_file = "data/demo_biometrics.json"
    if os.path.exists(store_file):
        try:
            os.remove(store_file)
        except Exception:
            pass

    # Initialize Backend Pipeline Components
    config = UIConfiguration(
        face_camera_index=0,
        face_match_threshold=0.80,
        face_enrollment_samples=3,
        face_capture_timeout=2.0
    )
    
    account_registry = AccountRegistry()
    credential_verifier = CredentialVerifier(account_registry)
    person_registry = PersonRegistry()
    
    face_store = FaceStore(store_path=store_file)
    camera_manager = CameraManager(camera_index=config.face_camera_index)
    face_detector = FaceDetector()
    face_encoder = FaceEncoder()
    
    face_verifier = OpenCVFaceVerifier(
        camera_manager=camera_manager,
        face_detector=face_detector,
        face_encoder=face_encoder,
        face_store=face_store,
        configuration=config
    )
    
    vision_client = OpenCVVisionIdentityClient(
        face_verifier=face_verifier,
        face_store=face_store,
        camera_manager=camera_manager,
        face_detector=face_detector,
        face_encoder=face_encoder,
        configuration=config
    )
    
    enrollment_service = EnrollmentService(person_registry, vision_client)
    session_manager = SessionManager()
    audit_log = AuthenticationAudit()
    
    auth_service = AuthenticationService(
        account_registry=account_registry,
        credential_verifier=credential_verifier,
        face_verifier=face_verifier,
        person_registry=person_registry,
        session_manager=session_manager,
        audit=audit_log
    )

    # Seed credentials account
    salt = secrets.token_hex(16)
    pw_hash = credential_verifier.hash_password("operator_key", bytes.fromhex(salt)).hex()
    acc = account_registry.create_account("operator_jack", pw_hash, salt, "USER")
    
    # Create corresponding Person profile
    person = person_registry.create_person(
        display_name="Jack Operator",
        account_id=acc.account_id,
        role="USER"
    )

    # --------------------------------------------------
    # SCENARIO 1 — Create person and enroll face
    # --------------------------------------------------
    print_title("SCENARIO 1: Create Person & Enroll Face from Camera")
    print(f"Person Profile Created:\nID: {person.atlas_person_id}\nName: {person.display_name}\nStatus: {person.status}\nBiometrics: {person.face_enrollment_status}")
    
    # Mock camera to return 5 frames with exactly one face
    dummy_cap = DummyVideoCapture(is_opened=True, num_frames=5)
    with patch.object(camera_manager, 'open_camera', return_value=dummy_cap):
        with patch.object(face_detector, 'detect_single_face', return_value=(0, 0, 10, 10)):
            success = enrollment_service.enroll_person_face(person.atlas_person_id, "enroll_raw")
            
    updated_p = person_registry.get_person(person.atlas_person_id)
    print(f"\nEnrollment Success: {success}")
    print(f"Updated Biometric State: {updated_p.face_enrollment_status}")
    print(f"Templates in FaceStore: {face_store.is_enrolled(person.atlas_person_id)}")

    # --------------------------------------------------
    # SCENARIO 2 — Correct username/password + matching face
    # --------------------------------------------------
    print_title("SCENARIO 2: Correct Credentials + Matching Face (Login Success)")
    
    dummy_cap_login = DummyVideoCapture(is_opened=True)
    with patch.object(camera_manager, 'open_camera', return_value=dummy_cap_login):
        with patch.object(face_detector, 'detect_single_face', return_value=(0, 0, 10, 10)):
            with patch.object(face_encoder, 'calculate_similarity', return_value=0.92):
                res = auth_service.login("operator_jack", "operator_key", "live_frame")
                
    print(f"Authenticated: {res['authenticated']}")
    print(f"Granted Role: {res['role']}")
    print(f"Session Token: {res['session_id']}")
    print(f"Message: {res['message']}")

    # --------------------------------------------------
    # SCENARIO 3 — Correct credentials + biometric mismatch
    # --------------------------------------------------
    print_title("SCENARIO 3: Correct Credentials + Biometric Mismatch (Login Denied)")
    
    dummy_cap_mismatch = DummyVideoCapture(is_opened=True)
    with patch.object(camera_manager, 'open_camera', return_value=dummy_cap_mismatch):
        with patch.object(face_detector, 'detect_single_face', return_value=(0, 0, 10, 10)):
            with patch.object(face_encoder, 'calculate_similarity', return_value=0.15): # poor similarity!
                res = auth_service.login("operator_jack", "operator_key", "live_frame")
                
    print(f"Authenticated: {res['authenticated']}")
    print(f"Session Token: {res['session_id']}")
    print(f"Message: {res['message']}")

    # --------------------------------------------------
    # SCENARIO 4 — Wrong password + face present
    # --------------------------------------------------
    print_title("SCENARIO 4: Wrong Password + Face Present (Login Denied)")
    
    # Should fail at credentials verification step, never opening the camera
    res = auth_service.login("operator_jack", "wrong_password", "live_frame")
    print(f"Authenticated: {res['authenticated']}")
    print(f"Message: {res['message']}")

    # --------------------------------------------------
    # SCENARIO 5 — Missing biometric enrollment
    # --------------------------------------------------
    print_title("SCENARIO 5: Missing Biometric Enrollment (Login Denied)")
    
    # Create new account without enrolling face
    temp_salt = secrets.token_hex(16)
    temp_hash = credential_verifier.hash_password("temp_key", bytes.fromhex(temp_salt)).hex()
    temp_acc = account_registry.create_account("temp_user", temp_hash, temp_salt, "USER")
    temp_person = person_registry.create_person("Temp User", temp_acc.account_id, "USER")
    
    # Login will perform dummy scan for timing protection and fail
    with patch.object(face_verifier, 'verify') as mock_verify:
        mock_verify.return_value = FaceVerificationResult(verified=False)
        res = auth_service.login("temp_user", "temp_key", "live_frame")
        
        # Verify dummy verify loop was called
        mock_verify.assert_called_with(person_id="ATLAS-P-DUMMY", biometric_input="live_frame")
        
    print(f"Authenticated: {res['authenticated']}")
    print(f"Message: {res['message']}")

    # --------------------------------------------------
    # SCENARIO 6 — Camera unavailable
    # --------------------------------------------------
    print_title("SCENARIO 6: Camera Unavailable (Safe Failure)")
    
    # Force CameraManager to fail during opening
    with patch.object(camera_manager, 'open_camera', side_effect=RuntimeError("Camera device is busy")):
        res = auth_service.login("operator_jack", "operator_key", "live_frame")
        
    print(f"Authenticated: {res['authenticated']}")
    print(f"Message: {res['message']}")

    # Cleanup demo database
    if os.path.exists(store_file):
        try:
            os.remove(store_file)
        except Exception:
            pass

    print("\nDemonstration complete.")

if __name__ == "__main__":
    main()
