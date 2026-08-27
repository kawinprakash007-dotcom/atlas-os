import os

def load_env_file():
    # Look for .env in current working dir or parent directory
    for base_dir in [os.getcwd(), os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))]:
        env_path = os.path.join(base_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()
            break

load_env_file()

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import cv2
import threading
import time

from atlas_ui.backend.vision.identity_cache import IdentityCache, BiometricCache
from atlas_ui.backend.vision.biometrics_manager import BiometricBindingManager
from atlas_ui.backend.vision.event_dispatcher import VisionEventDispatcher
from atlas_ui.backend.vision.recognition_worker import RecognitionWorker
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector

app = FastAPI(title="ATLAS Vision Edge Node")

# Global State
identity_cache = IdentityCache()
biometric_cache = BiometricCache()
binding_manager = BiometricBindingManager()
event_dispatcher = VisionEventDispatcher("http://127.0.0.1:8000/api/v1/events")

recognition_worker = RecognitionWorker(
    biometric_cache=biometric_cache,
    identity_cache=identity_cache,
    binding_manager=binding_manager,
    event_dispatcher=event_dispatcher
)

from atlas_ui.backend.vision.camera_manager import CameraManager
camera_manager = CameraManager(
    event_dispatcher=event_dispatcher,
    binding_manager=binding_manager,
    recognition_worker=recognition_worker
)

class IdentityPayload(BaseModel):
    person_id: str
    display_name: str
    role: str
    enabled: bool
    face_enrolled: bool

class SyncRequest(BaseModel):
    config_version: int
    persons: List[IdentityPayload]

class BiometricTemplatePayload(BaseModel):
    template_count: int
    enrolled_at: str
    vectors: List[List[float]]

class BiometricSyncRequest(BaseModel):
    biometric_config_version: int
    recognizer: str
    embedding_dimension: int
    timestamp: str
    templates: Dict[str, BiometricTemplatePayload]

@app.on_event("startup")
def on_startup():
    print("[Vision Edge] Starting Recognition Worker...")
    recognition_worker.start()
    print("[Vision Edge] Starting Camera Manager...")
    camera_manager.start()

@app.on_event("shutdown")
def on_shutdown():
    print("[Vision Edge] Stopping Recognition Worker...")
    recognition_worker.stop()
    print("[Vision Edge] Stopping Camera Manager...")
    camera_manager.stop()

@app.post("/api/v1/vision/sync")
def sync_identities(req: SyncRequest):
    # Reject TRACK-* IDs
    for p in req.persons:
        if p.person_id.startswith("TRACK-"):
            raise HTTPException(status_code=400, detail=f"Invalid authoritative ID: {p.person_id}")
            
    success = identity_cache.update_snapshot(req.config_version, [p.model_dump() for p in req.persons])
    if not success:
        return {"status": "ignored", "reason": "stale version"}
    return {"status": "success", "version": req.config_version}

@app.post("/api/v1/vision/biometric-sync")
def sync_biometrics(req: BiometricSyncRequest):
    for pid in req.templates.keys():
        if pid.startswith("TRACK-"):
            raise HTTPException(status_code=400, detail=f"Invalid authoritative ID: {pid}")
            
    success = biometric_cache.update_snapshot(
        req.biometric_config_version,
        req.recognizer,
        {k: v.model_dump() for k, v in req.templates.items()}
    )
    if not success:
        return {"status": "ignored", "reason": "stale version"}
    return {"status": "success", "version": req.biometric_config_version}

@app.get("/api/v1/vision/health")
def health_check():
    return {
        "status": "healthy",
        "identity_cache_size": len(identity_cache.get_all()),
        "biometric_cache_size": len(biometric_cache.get_templates()),
        "active_tracks": len(binding_manager.get_all_bindings())
    }
@app.get("/api/v1/vision/debug_cache")
def debug_cache():
    return {
        "identities": identity_cache.get_all(),
        "biometrics": list(biometric_cache.get_templates().keys())
    }
# Fake camera pipeline simulation for integration testing (avoids blocking main app)
@app.post("/api/v1/vision/test_track")
def inject_test_track(track_id: str):
    """
    Simulates a camera detecting a person and assigning a TRACK-* ID.
    """
    event_dispatcher.dispatch("PERSON_ENTERED", {"track_id": track_id})
    return {"status": "enqueued", "track_id": track_id}

@app.post("/api/v1/vision/test_recognition")
def inject_test_recognition(track_id: str, authoritative_id: str):
    """
    Bypasses the real camera/insightface pipeline for automated backend testing,
    simulating a successful recognition IF the person is in the cache and enabled.
    """
    identity = identity_cache.get_identity(authoritative_id)
    if identity and identity.get("enabled") is True and identity.get("face_enrolled") is True:
        binding_manager.bind(track_id, authoritative_id)
        event_dispatcher.dispatch(
            "PERSON_IDENTIFIED",
            {
                "track_id": track_id,
                "person_id": authoritative_id,
                "confidence": 0.99,
                "source": "TEST_MOCK"
            }
        )
        return {"status": "matched"}
    return {"status": "ignored_or_unauthorized"}

from fastapi.responses import Response

@app.get("/api/v1/vision/camera/status")
def get_camera_status():
    return camera_manager.get_status()

@app.post("/api/v1/vision/camera/start")
def start_camera():
    success = camera_manager.start()
    return {"success": success}

@app.post("/api/v1/vision/camera/stop")
def stop_camera():
    camera_manager.stop()
    return {"success": True}

@app.get("/api/v1/vision/camera/frame")
def get_camera_frame():
    frame = camera_manager.get_latest_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="Camera frame unavailable")
    ret, jpeg = cv2.imencode(".jpg", frame)
    if not ret:
        raise HTTPException(status_code=500, detail="Failed to encode frame")
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8002)
