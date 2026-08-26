import os
import sys
import time
import cv2
import numpy as np

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.insightface_recognizer import InsightFaceRecognizer
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore, TemplateStatus
from atlas_ui.backend.vision.cosine_similarity import best_cosine_similarity
from atlas_ui.backend.vision.face_quality import validate_face_quality
from atlas_ui.backend.vision import config

from atlas_ui.backend.vision.recognition_validation import (
    ValidationSample,
    ValidationReport,
    calculate_statistics,
    calibrate_threshold,
    generate_report_text,
    save_report_json
)

TARGET_PERSON_ID = "ATLAS-P-88888888"


class ValidationApp:
    def __init__(self, person_id: str):
        self.person_id = person_id
        self.store = FaceTemplateStore()
        
        status = self.store.get_template_status(person_id)
        if status != TemplateStatus.ENROLLED:
            print(f"[ERROR] No valid biometric enrollment found for {person_id}.")
            print(f"Status: {status.name}. Please enroll before running validation.")
            sys.exit(1)
            
        self.templates = self.store.get_templates(person_id)
        self.detector = YOLOFaceDetector()
        self.recognizer = InsightFaceRecognizer()
        self.camera = CameraManager(config.FACE_CAMERA_INDEX)
        
        self.current_scenario = ""
        self.current_status = ""
        self.progress_text = ""
        self.best_sim_display = 0.0
        self.faces_display = 0
        
        self.report = ValidationReport(
            person_id=person_id,
            model_name="insightface_buffalo_l",
            embedding_dimension=512,
            enrolled_template_count=len(self.templates),
            genuine_result=None,
            impostor_result=None,
            no_face_result=None,
            multiple_faces_result=None,
            pose_results={},
            lighting_results={}
        )

    def draw_hud(self, frame: np.ndarray):
        """Draws the Heads-Up Display on the given frame."""
        h, w = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, 150), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, f"Scenario: {self.current_scenario}", (10, 30), font, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"Progress: {self.progress_text}", (10, 60), font, 0.6, (200, 200, 200), 1)
        cv2.putText(frame, f"Faces detected: {self.faces_display}", (10, 90), font, 0.6, (200, 200, 200), 1)
        
        if self.best_sim_display > 0:
            color = (0, 255, 0) if self.best_sim_display >= config.FACE_MATCH_THRESHOLD else (0, 0, 255)
            cv2.putText(frame, f"Best Similarity: {self.best_sim_display:.4f}", (350, 30), font, 0.7, color, 2)
            
        cv2.putText(frame, f"Status: {self.current_status}", (350, 60), font, 0.6, (0, 255, 255), 1)
        return frame
        
    def wait_for_user(self, prompt: str) -> bool:
        """Shows prompt and waits for ENTER. Returns False if 'q' pressed."""
        print(f"\n>>> {prompt}")
        print(">>> Press ENTER in the terminal to begin, or 'q' to skip/abort.")
        cmd = input()
        if cmd.lower().strip() == 'q':
            return False
        return True
        
    def collect_samples(self, scenario_name: str, target_count: int, timeout_sec: int = 0) -> list:
        """
        Runs the camera loop to collect successful samples.
        If timeout_sec > 0, it stops after that duration regardless of count.
        Returns a list of ValidationSample.
        """
        self.current_scenario = scenario_name
        self.progress_text = f"0 / {target_count}"
        self.current_status = "COLLECTING"
        self.best_sim_display = 0.0
        
        samples = []
        start_time = time.time()
        
        print(f"\n[SCENARIO] {scenario_name}")
        
        try:
            if not self.camera.open():
                print("[ERROR] Could not open camera.")
                return samples
                
            while len(samples) < target_count or target_count == 0:
                now = time.time()
                if timeout_sec > 0 and (now - start_time) > timeout_sec:
                    break
                    
                frame = self.camera.read()
                if frame is None:
                    continue
                    
                self.faces_display = 0
                sample = ValidationSample(scenario=scenario_name, sample_number=len(samples)+1, similarity=0.0, accepted=False, reason="")
                
                det_res = self.detector.detect(frame)
                self.faces_display = det_res.face_count
                
                if det_res.face_count == 0:
                    sample.reason = "NO_FACE"
                    self.current_status = "REJECTED: NO FACE"
                elif det_res.face_count > 1:
                    sample.reason = "MULTIPLE_FACES"
                    self.current_status = "REJECTED: MULTIPLE FACES"
                else:
                    face = det_res.faces[0]
                    x1, y1, x2, y2 = face.bbox
                    
                    # Optional: draw bbox
                    display_frame = frame.copy()
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    
                    qual_res = validate_face_quality(frame, face.bbox)
                    if not qual_res.accepted:
                        sample.reason = qual_res.reason
                        self.current_status = f"QUALITY_FAIL: {qual_res.reason}"
                    else:
                        emb_res = self.recognizer.encode(frame, face.bbox)
                        if not emb_res.success:
                            sample.reason = "ENCODE_FAIL"
                            self.current_status = "ENCODE_FAIL"
                        else:
                            # Compare against templates
                            sim_res = best_cosine_similarity(emb_res.embedding, self.templates)
                            sample.similarity = sim_res.best_similarity
                            sample.accepted = True
                            sample.reason = "ACCEPTED"
                            
                            self.best_sim_display = sample.similarity
                            self.current_status = "ACCEPTED"
                            samples.append(sample)
                            self.progress_text = f"{len(samples)} / {target_count}"
                            
                            print(f"{scenario_name}: {len(samples)}/{target_count} | sim={sample.similarity:.4f}")
                            time.sleep(0.3) # Space out samples
                            
                # Display HUD
                display_frame = self.draw_hud(frame)
                cv2.imshow("Biometric Validation", display_frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    print("[ABORT] User aborted scenario collection.")
                    break
                    
        finally:
            self.camera.release()
            cv2.destroyAllWindows()
            
        return samples
        
    def run_all(self):
        print("\n" + "="*50)
        print("ATLAS OS REAL-WORLD BIOMETRIC VALIDATION")
        print("="*50)
        
        # 1. Genuine
        if self.wait_for_user("SCENARIO 1/6: AUTHORIZED PERSON. Look at the camera."):
            samps = self.collect_samples("AUTHORIZED PERSON", 15)
            self.report.genuine_result = calculate_statistics(samps)
        else:
            self.report.genuine_result = calculate_statistics([])
            
        # 2. Impostor
        if self.wait_for_user("SCENARIO 2/6: IMPOSTOR TEST. Have a DIFFERENT person look at the camera."):
            samps = self.collect_samples("IMPOSTOR PERSON", 15)
            self.report.impostor_result = calculate_statistics(samps)
        else:
            print("Skipping Impostor test.")
            self.report.impostor_result = calculate_statistics([])
            
        # 3. No Face
        if self.wait_for_user("SCENARIO 3/6: NO FACE. Move completely OUT of frame for 5 seconds."):
            # target_count=0 means run until timeout
            samps = self.collect_samples("NO FACE", 0, timeout_sec=5)
            # A pass means NO accepted samples
            self.report.no_face_result = calculate_statistics(samps)
        else:
            self.report.no_face_result = calculate_statistics([])
            
        # 4. Multiple Faces
        if self.wait_for_user("SCENARIO 4/6: MULTIPLE FACES. Bring TWO OR MORE faces into frame for 5 seconds."):
            samps = self.collect_samples("MULTIPLE FACES", 0, timeout_sec=5)
            self.report.multiple_faces_result = calculate_statistics(samps)
        else:
            self.report.multiple_faces_result = calculate_statistics([])
            
        # 5. Pose Robustness
        print("\n[SCENARIO 5/6] POSE ROBUSTNESS")
        for pose in ["FRONT", "LEFT", "RIGHT", "UP", "DOWN"]:
            if self.wait_for_user(f"Turn your head slightly: {pose}"):
                samps = self.collect_samples(f"POSE {pose}", 5)
                self.report.pose_results[pose] = calculate_statistics(samps)
            else:
                self.report.pose_results[pose] = calculate_statistics([])
                
        # 6. Lighting Robustness
        print("\n[SCENARIO 6/6] LIGHTING ROBUSTNESS")
        for light in ["NORMAL", "BRIGHT", "LOW LIGHT"]:
            if self.wait_for_user(f"Adjust lighting to: {light}"):
                samps = self.collect_samples(f"LIGHTING {light}", 5)
                self.report.lighting_results[light] = calculate_statistics(samps)
            else:
                self.report.lighting_results[light] = calculate_statistics([])
                
        # Calibration
        genuine_scores = [s.similarity for s in self.report.genuine_result.samples if s.accepted]
        impostor_scores = [s.similarity for s in self.report.impostor_result.samples if s.accepted]
        
        cal = calibrate_threshold(genuine_scores, impostor_scores)
        self.report.recommended_threshold = cal["recommended_threshold"]
        self.report.far_at_recommended = cal["far"]
        self.report.frr_at_recommended = cal["frr"]
        self.report.eer_approximation = cal["eer"]
        self.report.threshold_method = cal["method"]
        self.report.overall_status = cal["status"]
        
        # Generation
        report_txt = generate_report_text(self.report, config.FACE_MATCH_THRESHOLD)
        print("\n" + report_txt)
        
        # Save JSON
        json_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "recognition_validation_report.json"
        ))
        save_report_json(self.report, json_path)
        print(f"\n[INFO] Validation report saved to: {json_path}")


if __name__ == "__main__":
    app = ValidationApp(TARGET_PERSON_ID)
    try:
        app.run_all()
    except KeyboardInterrupt:
        print("\n[ABORT] Validation tool interrupted by user.")
        sys.exit(0)
