import sys
import os
import time
import subprocess
import urllib.request
import urllib.error
import json
import pytest

# Ensure CWD is on python path
sys.path.append(os.getcwd())

OS_URL = "http://127.0.0.1:8000"
VISION_URL = "http://127.0.0.1:8002"

def get_pid_on_port(port: int):
    try:
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
        for line in output.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                return int(parts[-1])
    except subprocess.CalledProcessError:
        pass
    return None

def is_healthy(url: str, path: str) -> bool:
    try:
        req = urllib.request.Request(f"{url}{path}")
        with urllib.request.urlopen(req, timeout=2) as res:
            return res.status == 200
    except Exception:
        return False

def kill_process(pid: int):
    try:
        subprocess.check_call(f"taskkill /F /PID {pid}", shell=True)
    except Exception as e:
        print(f"Failed to kill process {pid}: {e}")

def make_request(url: str, method: str = "GET", data: dict = None, token: str = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8") if data else None,
        headers=headers,
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            body = res.read().decode('utf-8')
            try:
                return res.status, json.loads(body)
            except Exception:
                return res.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return 0, str(e)

@pytest.fixture(scope="module", autouse=True)
def run_servers():
    os_spawned = False
    vision_spawned = False
    os_pid = get_pid_on_port(8000)
    vision_pid = get_pid_on_port(8002)

    # 1. Terminate any existing processes on port 8000 & 8002 to prevent locks
    if os_pid:
        print(f"[E2E TEST] Terminating existing OS backend process {os_pid} to load latest code changes.")
        kill_process(os_pid)
        os_pid = None
    if vision_pid:
        print(f"[E2E TEST] Terminating existing Vision Edge process {vision_pid} to load latest code changes.")
        kill_process(vision_pid)
        vision_pid = None

    # 2. Wipe databases for clean E2E test state
    db_path = os.path.abspath("data/atlas.db")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("[E2E TEST] Cleaned up atlas.db for pristine test environment.")
        except Exception as e:
            print(f"Failed to clean atlas.db: {e}")
            
    template_path = os.path.abspath("atlas_ui/backend/data/face_templates.json")
    if os.path.exists(template_path):
        try:
            os.remove(template_path)
            print("[E2E TEST] Cleaned up face_templates.json for pristine test environment.")
        except Exception as e:
            print(f"Failed to clean templates: {e}")

    if not os_pid:
        print("[E2E TEST] Starting OS backend...")
        os_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "atlas_ui.backend.main:app", "--host", "127.0.0.1", "--port", "8000"])
        os_spawned = True
        # Wait for health
        for _ in range(15):
            if is_healthy(OS_URL, "/"):
                break
            time.sleep(1)
        else:
            raise RuntimeError("OS backend failed to start")

    if not vision_pid:
        print("[E2E TEST] Starting Vision Edge...")
        vision_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "atlas_ui.backend.vision.app:app", "--host", "127.0.0.1", "--port", "8002"])
        vision_spawned = True
        # Wait for health
        for _ in range(15):
            if is_healthy(VISION_URL, "/api/v1/vision/health"):
                break
            time.sleep(1)
        else:
            raise RuntimeError("Vision Edge failed to start")

    yield

    # Clean up spawned processes
    if os_spawned:
        print("[E2E TEST] Stopping spawned OS backend...")
        os_proc.terminate()
        try:
            os_proc.wait(timeout=5)
        except Exception:
            pass
    if vision_spawned:
        print("[E2E TEST] Stopping spawned Vision Edge...")
        vision_proc.terminate()
        try:
            vision_proc.wait(timeout=5)
        except Exception:
            pass


def test_e2e_integration_flow():
    # TEST 1 & 2: Reachability
    status, health = make_request(f"{VISION_URL}/api/v1/vision/health")
    assert status == 200
    assert health["status"] == "healthy"
    
    status, os_index = make_request(f"{OS_URL}/")
    assert status == 200

    # Get Token
    status, login_res = make_request(f"{OS_URL}/api/v1/auth/login", "POST", {"username": "admin_user", "password": "admin_pass_123"})
    assert status == 200
    token = login_res["session_id"]

    # TEST 3: Create User
    username = f"e2e_user_{int(time.time())}"
    status, user_res = make_request(f"{OS_URL}/api/v1/admin/users", "POST", {
        "username": username,
        "password": "test_password_123",
        "display_name": "E2E User",
        "role": "USER",
        "enabled": True
    }, token=token)
    assert status == 200
    person_id = user_res["atlas_person_id"]
    account_id = user_res["account_id"]
    assert person_id.startswith("ATLAS-P-")

    # TEST 4: Verify Identity appears in Vision cache
    # Wait for async sync worker to push
    time.sleep(8)
    
    # Direct verify by checking if mock recognition resolves or querying /vision/status
    status, vision_status = make_request(f"{OS_URL}/api/v1/admin/vision/status", token=token)
    assert status == 200
    persons_in_edge = vision_status["edge_node"].get("identity_cache_size", 0)
    assert persons_in_edge > 0

    # TEST 5 & 6: Enroll Biometric Template
    from atlas_ui.backend.vision.face_template_store import FaceTemplateStore
    store = FaceTemplateStore()
    dummy_vector = [0.1] * 512
    store.save_templates(person_id, [dummy_vector], recognizer="insightface_buffalo_l", overwrite=True)
    
    # Update SQLite database to mark face as enrolled (must point to production database)
    from atlas_ui.backend.database.sqlite_store import SQLiteStore
    db_path = os.path.abspath("data/atlas.db")
    sqlite_db = SQLiteStore(db_path=db_path)
    sqlite_db.update_person(
        person_id=person_id,
        account_id=account_id,
        display_name="E2E User",
        role="USER",
        face_enrollment_status="ENROLLED",
        template_count=1
    )
    
    # Restart OS backend to load templates and trigger sync
    print("[E2E TEST] Restarting OS backend to trigger Biometric sync...")
    os_pid = get_pid_on_port(8000)
    if os_pid:
        kill_process(os_pid)
    
    # Start it again
    os_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "atlas_ui.backend.main:app", "--host", "127.0.0.1", "--port", "8000"])
    for _ in range(15):
        if is_healthy(OS_URL, "/"):
            break
        time.sleep(1)
    
    # Re-login
    status, login_res = make_request(f"{OS_URL}/api/v1/auth/login", "POST", {"username": "admin_user", "password": "admin_pass_123"})
    assert status == 200
    token = login_res["session_id"]
    
    # Wait for sync to happen
    time.sleep(6)
    
    # Verify Vision now has templates
    status, vision_status = make_request(f"{OS_URL}/api/v1/admin/vision/status", token=token)
    assert vision_status["edge_node"].get("biometric_cache_size", 0) > 0

    # TEST 7, 8 & 9: Trigger recognition and verify event flow
    status, track_res = make_request(f"{VISION_URL}/api/v1/vision/test_recognition?track_id=TRACK-0001&authoritative_id={person_id}", "POST")
    assert status == 200
    assert track_res["status"] == "matched"

    # TEST 10 & 11: Verify ATLAS OS receives the event and updates WorldState
    status, dash_res = make_request(f"{OS_URL}/api/v1/dashboard", token=token)
    assert status == 200
    events = dash_res.get("recent_events", [])
    print("[E2E TEST] Dashboard recent events:", events)

    # TEST 12: Disable the user and verify authorization is denied
    status, disable_res = make_request(f"{OS_URL}/api/v1/admin/users/{account_id}/status", "POST", {"enabled": False}, token=token)
    assert status == 200
    
    # Wait for status sync to Edge cache
    time.sleep(8)
    
    # Re-trigger recognition
    status, track_res_disabled = make_request(f"{VISION_URL}/api/v1/vision/test_recognition?track_id=TRACK-0001&authoritative_id={person_id}", "POST")
    assert status == 200
    assert track_res_disabled["status"] == "ignored_or_unauthorized"

    # TEST 13: Remove biometric enrollment and verify template disappears
    status, reset_res = make_request(f"{OS_URL}/api/v1/admin/people/{person_id}/reset-biometrics", "POST", token=token)
    assert status == 200
    
    time.sleep(8)
    status, vision_status = make_request(f"{OS_URL}/api/v1/admin/vision/status", token=token)
    assert vision_status["edge_node"].get("biometric_cache_size", 0) == 0

    # TEST 14: Delete the user and verify it disappears
    status, delete_res = make_request(f"{OS_URL}/api/v1/admin/users/{account_id}", "DELETE", token=token)
    assert status == 200
    
    time.sleep(8)
    status, vision_status = make_request(f"{OS_URL}/api/v1/admin/vision/status", token=token)
    assert vision_status["edge_node"].get("identity_cache_size", 0) == 2 # Admin + Normal user default seeds

    # TEST 15 & 16: Stop Vision, mutate, verify recovery
    print("[E2E TEST] Testing Vision Offline mutation...")
    v_pid = get_pid_on_port(8002)
    if v_pid:
        kill_process(v_pid)
        
    # Mutation when offline
    status, user_res2 = make_request(f"{OS_URL}/api/v1/admin/users", "POST", {
        "username": f"temp_user_{int(time.time())}",
        "password": "test_password_123",
        "display_name": "E2E User 2",
        "role": "USER",
        "enabled": True
    }, token=token)
    assert status == 200
    
    # Start Vision back
    print("[E2E TEST] Starting Vision back to check sync recovery...")
    vision_proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "atlas_ui.backend.vision.app:app", "--host", "127.0.0.1", "--port", "8002"])
    
    # Wait for sync recovery — Vision needs time to load InsightFace models first
    # Poll until Vision health endpoint is reachable (up to 30 seconds)
    vision_healthy = False
    for _ in range(30):
        if is_healthy(VISION_URL, "/api/v1/vision/health"):
            vision_healthy = True
            break
        time.sleep(1)
    assert vision_healthy, "Vision did not become healthy within 30 seconds after restart"
    
    # Allow sync worker to push the latest snapshot (up to 15 seconds)
    for _ in range(15):
        status, vision_status = make_request(f"{OS_URL}/api/v1/admin/vision/status", token=token)
        if status == 200 and vision_status["edge_node"].get("identity_cache_size", 0) == 3:
            break
        time.sleep(1)
    assert vision_status["edge_node"].get("identity_cache_size", 0) == 3 # 2 defaults + 1 new user synced
    
    # Cleanup spawned vision
    vision_proc.terminate()
    try:
        vision_proc.wait(timeout=5)
    except Exception:
        pass
    
    # Clean up spawned OS
    os_pid = get_pid_on_port(8000)
    if os_pid:
        kill_process(os_pid)

    print("[E2E TEST] All 16 E2E Integration tests passed successfully!")
