# Walkthrough — ATLAS OS v1.9 Real Local Biometric Pipeline

This walkthrough documents the design architecture, OpenCV 5.0 YuNet implementation details, security boundaries, API/routing integrations, test coverage, and execution results for the Real Local Biometric Pipeline and the Bootstrap Enrollment Mechanism.

---

## 1. Directory Structure & Files Updated

```text
ATLAS_OS/
└── atlas_ui/
    ├── backend/
    │   ├── configuration.py          (Biometric thresholds & camera parameters)
    │   ├── main.py                   (Production wiring & temporary bootstrap endpoint)
    │   │
    │   ├── biometric/
    │   │   ├── __init__.py           (Package exports)
    │   │   ├── face_verifier.py      (FaceVerifier abstract interface)
    │   │   ├── camera_manager.py     (Camera hardware lifecycles)
    │   │   ├── face_detector.py      (CNN-based YuNet face detector)
    │   │   ├── face_encoder.py       (Normalizes face ROIs to L2 unit vectors)
    │   │   ├── face_store.py         (Disk-persisted JSON biometrics store)
    │   │   ├── opencv_face_verifier.py (Production face verification runner)
    │   │   └── mock_face_verifier.py (Mock verifier kept for unit testing)
    │   │
    │   ├── identity/
    │   │   └── vision_identity_client.py (OpenCVVisionIdentityClient enrollment loops)
    │   │
    │   └── services/
    │       └── authentication_service.py (FaceVerifier interface & backwards adapter)
    │
    ├── frontend/
    │   ├── pages/
    │   │   ├── login.js             (Login state transitions & temporary INITIAL ADMIN FACE SETUP option)
    │   │   └── admin_dashboard.js   (Register Face modal & live progress indicators)
    │   └── index.css                (Modal overlays & laser scan animations)
    │
    ├── tests/
    │   └── test_biometric.py        (Tests covering 18 biometric rules + 10 bootstrap validation rules)
    │
    └── demo_real_face_authentication.py (Interactive verification demo covering 6 scenarios)
```

---

## 2. Core Architectural Design

- **OpenCV 5.0 YuNet CNN Face Detector**: Since the latest `opencv-python==5.0.0.93` completely deprecates the traditional Haar Cascade class `CascadeClassifier`, we transitioned the pipeline to OpenCV 5's built-in deep-learning face detector `FaceDetectorYN` (YuNet). We download the pre-trained `face_detection_yunet_2023mar.onnx` model automatically and instantiate the detector with dynamic frame input sizes. It enforces the "exactly one face" constraint (rejecting 0 or >1 faces).
- **L2 Normalized Cosine Similarity Matching**: Once a face is cropped, it is converted to grayscale, resized to `64x64`, histogram-equalized to minimize lighting variance, and L2-normalized. We use Cosine Similarity (dot product) to compare vectors against multiple enrolled templates in the store.
- **Disk-persisted Face Store**: Templates are saved inside `atlas_ui/data/biometrics.json` mapping `atlas_person_id` to template lists, loading on startup and persisting changes safely.
- **Backwards-Compatibility Adapter**: To prevent breaking existing test cases that pass `vision_client` via keyword arguments, `AuthenticationService` constructor accepts either `face_verifier` or `vision_client`, wrapping the latter inside a `VisionClientAdapter` that implements the standard `FaceVerifier` interface.

---

## 3. Temporary Admin Biometric Bootstrap Enrollment

To allow the initial administrator profile face registration, a temporary endpoint and setup flow were created:

### Temporary Endpoint
- **URL**: `POST /api/v1/auth/bootstrap/enroll`
- **Clearing Code**: Marked with `# TEMPORARY INITIAL SETUP ONLY — REMOVE AFTER ADMIN BIOMETRIC ENROLLMENT`.
- **Logic**:
  1. Accepts `username` and `password`.
  2. Verifies credentials against `CredentialVerifier`.
  3. Validates account is `enabled` and role is `ADMIN`.
  4. Resolves `atlas_person_id`.
  5. Refuses registration if already `ENROLLED` (returns 400).
  6. Opens camera via `CameraManager`, runs sample capture, encodes profiles, saves in `FaceStore`, and sets state to `ENROLLED`.
  7. **No session is created** by this endpoint.
  8. If credentials fail, returns a generic `"Authentication failed"` message.

### Frontend Flow
- A dashed button `INITIAL ADMIN FACE SETUP` is added on the login page.
- Triggers a setup modal showing a clear warning that this is for first-time administrator enrollment.
- Feeds username and password, then displays progress states:
  - `"Connecting to DroidCam..."`
  - `"Position exactly one face in camera"`
  - `"Capturing biometric samples: X / 5"`
- Shows success message: `"Biometric profile enrolled successfully. Please log in again using username, password, and live face verification."` without automatic login.

---

## 4. Test Verification Outcomes

- **Existing Core Tests**: **190/190 passed**
- **Existing and New UI/Biometric/Bootstrap Tests**: **38/38 passed** (covering camera release, multiple face rejections, inactive person enrollments, mismatch rejections, and exposure blocks).

**Total tests passing: 228.**

---

## 5. How to Run

### Run Unit Tests
```powershell
$env:PYTHONPATH="."
python -m pytest atlas_ui/tests/ -q
python -m pytest tests/ -q
```

### Run Verification Demo
```powershell
$env:PYTHONPATH="."
python atlas_ui/demo_real_face_authentication.py
```
