import threading
import time
import json
import urllib.request
import urllib.error
from typing import Optional

class VisionSyncState:
    def __init__(self):
        self.lock = threading.RLock()
        
        self.identity_dirty = True
        self.biometric_dirty = True
        
        self.identity_version = 0
        self.biometric_version = 0
        
        self.retry_count = 0
        self.next_retry_at = 0.0

    def mark_identity_dirty(self):
        with self.lock:
            self.identity_dirty = True
            self.identity_version += 1
            self.retry_count = 0
            self.next_retry_at = 0.0
            
    def mark_biometric_dirty(self):
        with self.lock:
            self.biometric_dirty = True
            self.biometric_version += 1
            self.retry_count = 0
            self.next_retry_at = 0.0

class VisionSyncWorker:
    def __init__(
        self, 
        identity_memory, 
        face_template_store,
        target_url: str = "http://127.0.0.1:8002"
    ):
        self.identity_memory = identity_memory
        self.face_template_store = face_template_store
        self.target_url = target_url
        self.state = VisionSyncState()
        
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self):
        print("[VisionSyncWorker] Started.")
        while not self._stop_event.is_set():
            now = time.time()
            
            with self.state.lock:
                needs_sync = self.state.identity_dirty or self.state.biometric_dirty
                can_retry = now >= self.state.next_retry_at
                
            if needs_sync and can_retry:
                self._attempt_sync()
            
            time.sleep(1.0)

    def _send_payload(self, path: str, payload: dict) -> bool:
        url = f"{self.target_url}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as res:
                return res.status == 200
        except Exception as e:
            print(f"[VisionSyncWorker] Failed to sync {path}: {e}")
            return False

    def _attempt_sync(self):
        success = True
        
        # 1. Sync Identities First
        with self.state.lock:
            id_dirty = self.state.identity_dirty
            id_ver = self.state.identity_version
            
        if id_dirty:
            # Build fresh snapshot
            try:
                # Assuming identity_memory has a way to get all identities
                # Depending on how identity_memory is implemented...
                # We will just fetch everything
                all_ids = self.identity_memory.get_all_identities()
                payload = {
                    "config_version": id_ver,
                    "persons": []
                }
                for data in all_ids:
                    # Handle if data is an object or a dict
                    d = data if isinstance(data, dict) else data.__dict__
                    pid = d.get("person_id")
                    if not pid:
                        continue
                    payload["persons"].append({
                        "person_id": pid,
                        "display_name": d.get("display_name", "Unknown"),
                        "role": d.get("role", "USER"),
                        "enabled": d.get("enabled", True),
                        "face_enrolled": d.get("face_enrolled", False)
                    })
                
                if self._send_payload("/api/v1/vision/sync", payload):
                    with self.state.lock:
                        self.state.identity_dirty = False
                else:
                    success = False
            except Exception as e:
                print(f"[VisionSyncWorker] Identity Sync Snapshot Error: {e}")
                success = False

        # 2. Sync Biometrics Only If Identities Succeeded
        with self.state.lock:
            bio_dirty = self.state.biometric_dirty
            bio_ver = self.state.biometric_version
            
        if success and bio_dirty:
            try:
                # Assuming face_template_store has list_enrolled_people and get_templates
                enrolled_people = self.face_template_store.list_enrolled_people()
                
                # Filter to valid dictionary structure
                formatted_templates = {}
                for pid in enrolled_people:
                    vectors = self.face_template_store.get_templates(pid)
                    if not vectors:
                        vectors = []
                    
                    formatted_templates[pid] = {
                        "template_count": len(vectors),
                        "enrolled_at": "2026-08-27T00:00:00Z", # Placeholder timestamp as store might not track it per template list
                        "vectors": vectors
                    }
                
                payload = {
                    "biometric_config_version": bio_ver,
                    "recognizer": "insightface_buffalo_l",
                    "embedding_dimension": 512,
                    "timestamp": "2026-08-27T00:00:00Z",
                    "templates": formatted_templates
                }
                
                if self._send_payload("/api/v1/vision/biometric-sync", payload):
                    with self.state.lock:
                        self.state.biometric_dirty = False
                else:
                    success = False
            except Exception as e:
                print(f"[VisionSyncWorker] Biometric Sync Snapshot Error: {e}")
                success = False
                
        # Handle Failure (Exponential Backoff)
        with self.state.lock:
            if success:
                self.state.retry_count = 0
            else:
                self.state.retry_count += 1
                backoff = min(60, 2 ** self.state.retry_count) # Max 60 seconds
                self.state.next_retry_at = time.time() + backoff
                print(f"[VisionSyncWorker] Sync failed. Retrying in {backoff}s")
