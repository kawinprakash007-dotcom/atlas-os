"""
Standalone test for ArcFace recognizer.
Captures ONE real frame via DroidCam, detects one face, and generates an embedding.
Does NOT require the full enrollment loop.
"""
import sys
import numpy as np

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.arcface_recognizer import ArcFaceRecognizer

def main():
    print("==================================================", flush=True)
    print("ATLAS OS — ArcFace Recognizer Standalone Test", flush=True)
    print("==================================================", flush=True)

    # 1. Load detector and recognizer
    detector = YOLOFaceDetector(conf_threshold=0.50)
    recognizer = ArcFaceRecognizer()

    # 2. Capture one frame
    print("\n[TEST] Opening camera and capturing one frame...", flush=True)
    try:
        with CameraManager(camera_index=0) as cam:
            frame = cam.capture_frame()
    except Exception as e:
        print(f"[TEST] Camera error: {e}", flush=True)
        sys.exit(1)

    print(f"[TEST] Frame captured: shape={frame.shape} dtype={frame.dtype}", flush=True)

    # 3. Detect face
    result = detector.detect(frame)
    print(f"[TEST] Faces detected: {result.face_count}", flush=True)
    if result.no_face:
        print("[TEST] FAIL — No face detected. Please ensure your face is visible.", flush=True)
        sys.exit(1)
    if result.multiple_faces:
        print("[TEST] FAIL — Multiple faces detected. Please ensure only one face is visible.", flush=True)
        sys.exit(1)

    face = result.faces[0]
    bbox = face.bbox
    print(f"[TEST] Face detected: conf={face.confidence:.4f}  bbox={bbox}", flush=True)

    # 4. Crop face
    x1, y1, x2, y2 = bbox
    crop = frame[y1:y2, x1:x2]
    print(f"[TEST] Crop shape: {crop.shape}  dtype={crop.dtype}  "
          f"min={int(crop.min())}  max={int(crop.max())}", flush=True)

    # 5. Generate embedding
    print("\n[TEST] Generating face embedding...", flush=True)
    emb_result = recognizer.encode(crop)

    if not emb_result.success:
        print(f"[TEST] FAIL — Embedding generation failed: {emb_result.error}", flush=True)
        sys.exit(1)

    emb = np.array(emb_result.embedding)
    norm = float(np.linalg.norm(emb))

    print(f"\n[TEST] ===== RESULTS =====", flush=True)
    print(f"[TEST] Embedding dimension : {emb_result.embedding_dimension}", flush=True)
    print(f"[TEST] L2 norm             : {norm:.6f}", flush=True)
    print(f"[TEST] All finite          : {np.isfinite(emb).all()}", flush=True)
    print(f"[TEST] First 5 values      : {[round(v, 6) for v in emb[:5]]}", flush=True)
    print(f"[TEST] STATUS              : SUCCESS", flush=True)
    print(f"[TEST] =====================", flush=True)

if __name__ == "__main__":
    main()
