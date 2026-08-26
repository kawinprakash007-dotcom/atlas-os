import os

# Camera Configuration
FACE_CAMERA_INDEX = 0

# Active recognizer identifier
# Must match FaceTemplateStore.RECOGNIZER_ID for templates to be accepted.
ACTIVE_RECOGNIZER = "insightface_buffalo_l"

# Biometric Verification Threshold
#
# PLACEHOLDER — calibrate using test_threshold_calibration.py before production use.
#
# InsightFace buffalo_l (ArcFace ResNet50 with 5-point alignment):
#   Expected genuine (same person)  : 0.4 – 0.8
#   Expected impostor (diff person) : 0.0 – 0.3
#   (Wide separation band vs garavv model which had 0.95 noise floor)
#
# Previous model (garavv/arcface-onnx):
#   Random-noise floor: mean=0.9495, max=0.9775 — unusable without >0.985 threshold.
#   Retired. All old templates are LEGACY and require re-enrollment.
#
# Current value: conservative starting point pending real calibration.
# Run: python -m atlas_ui.backend.vision.test_threshold_calibration
FACE_MATCH_THRESHOLD = 0.35

# InsightFace buffalo_l bbox-match tolerance (pixels)
# Max distance between YOLO bbox centre and InsightFace detected bbox centre
# to consider them the same face.
INSIGHTFACE_BBOX_TOLERANCE_PX = 80

# Face Quality Thresholds
MIN_FACE_WIDTH = 80
MIN_FACE_HEIGHT = 80
MIN_BLUR_LAPLACIAN_VAR = 50.0
MIN_BRIGHTNESS = 40.0
MAX_BRIGHTNESS = 220.0

# Enrollment Configuration
ENROLL_SAMPLES_REQUIRED = 5
MIN_SAMPLE_INTERVAL_SECONDS = 0.5
MAX_DUPLICATE_SIMILARITY = 0.98

# Verification Configuration
# Number of accepted frames whose similarity scores are median-aggregated
# before a verification decision is made.
VERIFY_OBSERVATION_FRAMES = 5
