import cv2
import sys
import time

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.arcface_recognizer import ArcFaceRecognizer
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore
from atlas_ui.backend.vision.face_enrollment_service import FaceEnrollmentService
from atlas_ui.backend.vision.face_quality import validate_face_quality
from atlas_ui.backend.vision import config

def main():
    person_id = "test-operator-1"
    
    print("==================================================", flush=True)
    print("ATLAS OS Live Face Enrollment Tool", flush=True)
    print(f"Target Person ID: {person_id}", flush=True)
    print("Press 'q' or 'Q' to quit.", flush=True)
    print("==================================================", flush=True)

    # 1. Initialize detector, recognizer, and template store
    detector = YOLOFaceDetector(conf_threshold=0.50)
    recognizer = ArcFaceRecognizer()
    store = FaceTemplateStore()
    enroll_service = FaceEnrollmentService(detector, recognizer, store)

    # Clear previous templates for a clean test run
    store.remove_templates(person_id)

    templates = []
    last_capture_time = 0.0
    samples_rejected = 0

    print("[CAMERA] Initializing CameraManager on index 0...", flush=True)
    try:
        with CameraManager(camera_index=0) as camera:
            print("[CAMERA] Camera ready. Face the camera for enrollment...", flush=True)
            
            while len(templates) < config.ENROLL_SAMPLES_REQUIRED:
                frame = camera.capture_frame()
                display_frame = frame.copy()
                
                # YOLO detection
                detection_res = detector.detect(frame)
                
                # Default HUD state
                hud_text = "NO FACE"
                hud_color = (0, 0, 255)  # Red
                quality_str = ""
                
                if detection_res.single_face:
                    face = detection_res.faces[0]
                    bbox = face.bbox
                    x1, y1, x2, y2 = bbox
                    
                    hud_text = "FACE DETECTED"
                    hud_color = (255, 255, 0)  # Yellow
                    
                    # Quality Check
                    q_res = validate_face_quality(frame, bbox)
                    if q_res.accepted:
                        quality_str = "QUALITY ACCEPTED"
                        hud_color = (0, 255, 0)  # Green
                        
                        # Process / capture sample
                        embedding, reject_reason, cap_time = enroll_service.process_frame(
                            frame, templates, last_capture_time
                        )
                        if embedding is not None:
                            templates.append(embedding)
                            last_capture_time = cap_time
                            print(f"[ENROLLMENT] Successfully captured sample {len(templates)}/{config.ENROLL_SAMPLES_REQUIRED}", flush=True)
                        else:
                            if reject_reason != "SAMPLE_TOO_QUICK":
                                quality_str = f"REJECTED: {reject_reason}"
                                samples_rejected += 1
                    else:
                        # Extract primary quality reason
                        if "below minimum threshold" in q_res.reason:
                            quality_str = "FACE TOO SMALL"
                        elif "too blurry" in q_res.reason:
                            quality_str = "FACE TOO BLURRY"
                        elif "too dark" in q_res.reason:
                            quality_str = "LIGHTING TOO DARK"
                        elif "too bright" in q_res.reason:
                            quality_str = "LIGHTING TOO BRIGHT"
                        else:
                            quality_str = "QUALITY REJECTED"
                    
                    # Draw box and status on face
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), hud_color, 2)
                    cv2.putText(
                        display_frame,
                        quality_str,
                        (x1, max(15, y1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        hud_color,
                        2
                    )

                elif detection_res.multiple_faces:
                    hud_text = "MULTIPLE FACES"
                    hud_color = (0, 165, 255)  # Orange
                    
                    for face in detection_res.faces:
                        x1, y1, x2, y2 = face.bbox
                        cv2.rectangle(display_frame, (x1, y1), (x2, y2), hud_color, 2)

                # Draw top status banner
                cv2.putText(
                    display_frame,
                    hud_text,
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    hud_color,
                    2,
                    cv2.LINE_AA
                )
                
                # Draw enrollment progress
                cv2.putText(
                    display_frame,
                    f"SAMPLES: {len(templates)} / {config.ENROLL_SAMPLES_REQUIRED}",
                    (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA
                )

                cv2.imshow("ATLAS OS - Face Enrollment Studio", display_frame)

                # Q to quit
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == ord('Q'):
                    print("[SYSTEM] Enrollment aborted by user.", flush=True)
                    break
            
            # Save templates if we successfully collected all
            if len(templates) == config.ENROLL_SAMPLES_REQUIRED:
                store.save_templates(person_id, templates, overwrite=True)
                print(f"[SYSTEM] Enrollment completed and saved for person '{person_id}'!", flush=True)

    except Exception as e:
        print(f"[ERROR] Enrollment failed: {e}", flush=True)
    finally:
        cv2.destroyAllWindows()
        print("[SYSTEM] Windows and camera released.", flush=True)

if __name__ == "__main__":
    main()
