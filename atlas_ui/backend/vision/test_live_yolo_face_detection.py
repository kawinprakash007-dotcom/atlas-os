import cv2
import sys
import time

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector

def main():
    print("==================================================", flush=True)
    print("YOLO Face Detection Live Test", flush=True)
    print("Press 'q' or 'Q' inside the video window to quit.", flush=True)
    print("==================================================", flush=True)

    # 1. Initialize YOLOFaceDetector
    try:
        detector = YOLOFaceDetector(conf_threshold=0.50)
        print("[YOLO] Face detection model loaded.", flush=True)
    except Exception as e:
        print(f"[YOLO] Failed to load model: {e}", flush=True)
        sys.exit(1)

    # 2. Initialize CameraManager
    camera_index = 0
    print(f"[CAMERA] Initializing CameraManager on index {camera_index}...", flush=True)
    
    try:
        with CameraManager(camera_index=camera_index) as camera:
            print("[CAMERA] Camera initialized successfully. Starting live stream...", flush=True)
            
            last_log_time = 0.0
            
            while True:
                # Capture frame
                frame = camera.capture_frame()
                
                # Run YOLO face detection inference
                result = detector.detect(frame)
                
                # Check status
                status = result.status
                faces = result.faces
                face_count = result.face_count
                
                # Setup display text and color based on status
                if status == "NO_FACE":
                    hud_text = "NO FACE DETECTED"
                    hud_color = (0, 0, 255)  # Red (BGR)
                elif status == "SINGLE_FACE":
                    hud_text = "ONE FACE DETECTED"
                    hud_color = (0, 255, 0)  # Green
                else:
                    hud_text = "MULTIPLE FACES DETECTED"
                    hud_color = (0, 165, 255)  # Orange/Yellow
                
                # Rate-limited console logs (once per 2 seconds to avoid console spam)
                current_time = time.time()
                if current_time - last_log_time >= 2.0:
                    print(f"[DETECTION] Status: {hud_text} | Faces: {face_count}", flush=True)
                    for i, face in enumerate(faces):
                        print(f"  - Face {i}: conf={face.confidence:.4f}, bbox={face.bbox}", flush=True)
                    last_log_time = current_time
                
                # Draw detections on frame
                for face in faces:
                    x1, y1, x2, y2 = face.bbox
                    # Draw bounding box
                    cv2.rectangle(frame, (x1, y1), (x2, y2), hud_color, 2)
                    # Draw label with confidence score
                    label = f"Face: {face.confidence:.2f}"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(15, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        hud_color,
                        2
                    )
                
                # Render HUD status banner in the top-left corner
                cv2.putText(
                    frame,
                    hud_text,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    hud_color,
                    2,
                    cv2.LINE_AA
                )
                
                # Display HUD details (face count)
                cv2.putText(
                    frame,
                    f"Count: {face_count}",
                    (20, 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )
                
                # Show video stream
                cv2.imshow("ATLAS OS - YOLO Face Detection Baseline", frame)
                
                # Check for exit key (q or Q)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    print("[SYSTEM] Exit key pressed. Closing stream...", flush=True)
                    break
                    
    except Exception as e:
        print(f"[ERROR] Live test encountered a runtime exception: {e}", flush=True)
    finally:
        cv2.destroyAllWindows()
        print("[SYSTEM] Camera released and windows destroyed cleanly.", flush=True)

if __name__ == "__main__":
    main()
