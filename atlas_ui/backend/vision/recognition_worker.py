import queue
import threading
import time
import numpy as np
from typing import Dict, Any, Optional

from atlas_ui.backend.vision.biometrics_manager import BiometricBindingManager
from atlas_ui.backend.vision.identity_cache import BiometricCache, IdentityCache
from atlas_ui.backend.vision.event_dispatcher import VisionEventDispatcher
from atlas_ui.backend.vision.insightface_recognizer import InsightFaceRecognizer
from atlas_ui.backend.vision.cosine_similarity import cosine_similarity

class RecognitionWorker:
    def __init__(
        self, 
        biometric_cache: BiometricCache, 
        identity_cache: IdentityCache,
        binding_manager: BiometricBindingManager,
        event_dispatcher: VisionEventDispatcher
    ):
        self.biometric_cache = biometric_cache
        self.identity_cache = identity_cache
        self.binding_manager = binding_manager
        self.event_dispatcher = event_dispatcher
        
        self.queue = queue.Queue(maxsize=10)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.recognizer = InsightFaceRecognizer()
        
    def start(self):
        self._thread.start()
        
    def stop(self):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
            
    def enqueue(self, track_id: str, frame: np.ndarray, bbox: list) -> bool:
        """
        Non-blocking enqueue. If queue is full, skip recognition.
        """
        if self.binding_manager.resolve(track_id):
            return False # Already resolved

        try:
            self.queue.put_nowait((track_id, frame, bbox))
            return True
        except queue.Full:
            return False
            
    def _run(self):
        print("[RecognitionWorker] Started.")
        # Models are lazy loaded on first recognition call
        
        while not self._stop_event.is_set():
            try:
                task = self.queue.get(timeout=1.0)
                track_id, frame, bbox = task
                self._process(track_id, frame, bbox)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[RecognitionWorker] Error processing task: {e}")
                
    def _process(self, track_id: str, frame: np.ndarray, bbox: list):
        if self.binding_manager.resolve(track_id):
            return # Bound in the meantime
            
        # 1. Extract Embedding
        result = self.recognizer.recognize(frame, bbox)
        if not result or not result.is_valid:
            return
            
        embedding = result.embedding
        if embedding is None:
            return
            
        # 2. Match against BiometricCache
        templates = self.biometric_cache.get_templates()
        if not templates:
            return
            
        best_match_id = None
        best_score = -1.0
        
        # Simple greedy search
        for person_id, data in templates.items():
            if not person_id.startswith("ATLAS-P-"):
                continue
            for vec in data.get("vectors", []):
                try:
                    score = cosine_similarity(embedding.tolist(), vec)
                    if score > best_score:
                        best_score = score
                        best_match_id = person_id
                except Exception as e:
                    print(f"Error comparing faces: {e}")
                    
        # Configurable threshold (e.g., 0.45 for ArcFace Cosine Similarity)
        if best_match_id and best_score > 0.45:
            # Check IdentityCache to ensure they are enabled
            identity = self.identity_cache.get_identity(best_match_id)
            if identity and identity.get("enabled") is True and identity.get("face_enrolled") is True:
                success = self.binding_manager.bind(track_id, best_match_id)
                if success:
                    print(f"[RecognitionWorker] Matched {track_id} to {best_match_id} (Score: {best_score:.2f})")
                    # Fire Event
                    self.event_dispatcher.dispatch(
                        "PERSON_IDENTIFIED",
                        {
                            "track_id": track_id,
                            "person_id": best_match_id,
                            "confidence": best_score,
                            "source": "ATLAS_VISION"
                        }
                    )
            else:
                print(f"[RecognitionWorker] Matched {track_id} to {best_match_id}, but identity is DISABLED or NOT FOUND.")
