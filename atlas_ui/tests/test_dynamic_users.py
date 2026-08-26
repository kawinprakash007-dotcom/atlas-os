import pytest
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app

client = TestClient(app)

ADMIN_USER = "admin_user"
ADMIN_PASS = "admin_pass_123"

def get_admin_session():
    # Login as seeded admin
    resp = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    if resp.status_code == 401 and resp.json().get("biometric_required"):
        pid = resp.json()["person_id"]
        tok = "p6_admin_token"
        app.state.auth_service.register_biometric_success(pid, tok)
        resp = client.post("/api/v1/auth/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASS,
            "biometric_input": tok,
        })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["session_id"]

def test_seeded_users_exist():
    sess = get_admin_session()
    resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"})
    assert resp.status_code == 200
    users = resp.json()["users"]
    
    # Check that admin_user and normal_user exist and their IDs are intact
    admin_u = next((u for u in users if u["username"] == "admin_user"), None)
    normal_u = next((u for u in users if u["username"] == "normal_user"), None)
    
    assert admin_u is not None
    assert admin_u["atlas_person_id"] == "ATLAS-P-88888888"
    
    assert normal_u is not None
    assert normal_u["atlas_person_id"] == "ATLAS-P-11111111"

def test_create_new_user():
    sess = get_admin_session()
    payload = {
        "username": "new_dynamic_user",
        "password": "secure_password",
        "display_name": "Dynamic User",
        "role": "USER",
        "enabled": True
    }
    resp = client.post("/api/v1/admin/users", json=payload, headers={"Authorization": f"Bearer {sess}"})
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["username"] == "new_dynamic_user"
    assert data["display_name"] == "Dynamic User"
    assert data["role"] == "USER"
    
    # Ensure ID generation worked
    assert data["atlas_person_id"].startswith("ATLAS-P-")
    assert data["atlas_person_id"] not in ["ATLAS-P-88888888", "ATLAS-P-11111111"]

def test_create_new_admin():
    sess = get_admin_session()
    payload = {
        "username": "new_dynamic_admin",
        "password": "secure_password",
        "display_name": "Dynamic Admin",
        "role": "ADMIN",
        "enabled": True
    }
    resp = client.post("/api/v1/admin/users", json=payload, headers={"Authorization": f"Bearer {sess}"})
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["username"] == "new_dynamic_admin"
    assert data["display_name"] == "Dynamic Admin"
    assert data["role"] == "ADMIN"
    assert data["atlas_person_id"].startswith("ATLAS-P-")

def test_duplicate_username_rejection():
    sess = get_admin_session()
    # Try creating a user with 'admin_user' username
    payload = {
        "username": "admin_user",
        "password": "secure_password",
        "display_name": "Imposter Admin",
        "role": "USER",
        "enabled": True
    }
    resp = client.post("/api/v1/admin/users", json=payload, headers={"Authorization": f"Bearer {sess}"})
    # The backend correctly translates the ValueError into a 400 Bad Request
    assert resp.status_code == 400

def test_new_user_appears_in_list():
    sess = get_admin_session()
    # Create
    payload = {
        "username": "test_list_user",
        "password": "secure_password",
        "display_name": "List User",
        "role": "USER",
        "enabled": True
    }
    client.post("/api/v1/admin/users", json=payload, headers={"Authorization": f"Bearer {sess}"})
    
    # Get list
    resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"})
    users = resp.json()["users"]
    
    found = next((u for u in users if u["username"] == "test_list_user"), None)
    assert found is not None
    assert found["display_name"] == "List User"
    assert found["atlas_person_id"].startswith("ATLAS-P-")

# ==============================================================================
# PHASE 2 TESTS: Advanced Dynamic User Lifecycle Management
# ==============================================================================

def test_edit_user_basic():
    sess = get_admin_session()
    # Create user to edit
    resp = client.post("/api/v1/admin/users", json={
        "username": "edit_target", "password": "pw", "display_name": "Old Name", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp.status_code == 200
    acc_id = resp.json()["account_id"]
    person_id = resp.json()["atlas_person_id"]

    # 1. Edit display name & 4. Edit role & 13. Person ID unchanged
    resp2 = client.put(f"/api/v1/admin/users/{acc_id}", json={
        "username": "edit_target", "display_name": "New Name", "role": "ADMIN", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 200

    resp3 = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"})
    u = next(u for u in resp3.json()["users"] if u["account_id"] == acc_id)
    assert u["display_name"] == "New Name"
    assert u["role"] == "ADMIN"
    assert u["atlas_person_id"] == person_id

    # 2. Edit username
    resp4 = client.put(f"/api/v1/admin/users/{acc_id}", json={
        "username": "edit_target_new", "display_name": "New Name", "role": "ADMIN", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp4.status_code == 200
    resp5 = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"})
    u2 = next(u for u in resp5.json()["users"] if u["account_id"] == acc_id)
    assert u2["username"] == "edit_target_new"

def test_duplicate_username_edit_rejection():
    sess = get_admin_session()
    resp = client.post("/api/v1/admin/users", json={
        "username": "dup_target", "password": "pw", "display_name": "Dup", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    acc_id = resp.json()["account_id"]

    # 3. Duplicate username rejection during edit
    resp2 = client.put(f"/api/v1/admin/users/{acc_id}", json={
        "username": "admin_user", "display_name": "Dup", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 400

def test_disable_and_reenable_user():
    sess = get_admin_session()
    client.post("/api/v1/admin/users", json={
        "username": "dis_target", "password": "pw", "display_name": "Dis Target", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    
    # login as the new user to create a session
    resp_login = client.post("/api/v1/auth/login", json={"username": "dis_target", "password": "pw"})
    assert resp_login.status_code == 200
    dis_sess = resp_login.json()["session_id"]
    
    # get acc_id
    users = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"}).json()["users"]
    acc_id = next(u["account_id"] for u in users if u["username"] == "dis_target")

    # 5. Disable user & 7. Existing sessions invalidated
    resp2 = client.put(f"/api/v1/admin/users/{acc_id}", json={
        "username": "dis_target", "display_name": "Dis Target", "role": "USER", "enabled": False
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 200
    
    # verify session invalidated (auth/me should fail)
    assert client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {dis_sess}"}).status_code == 401

    # 6. Disabled user cannot login
    resp3 = client.post("/api/v1/auth/login", json={"username": "dis_target", "password": "pw"})
    assert resp3.status_code == 401

    # 8. Re-enable user
    client.put(f"/api/v1/admin/users/{acc_id}", json={
        "username": "dis_target", "display_name": "Dis Target", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert client.post("/api/v1/auth/login", json={"username": "dis_target", "password": "pw"}).status_code == 200

def test_delete_user():
    sess = get_admin_session()
    resp = client.post("/api/v1/admin/users", json={
        "username": "del_target", "password": "pw", "display_name": "Del Target", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    acc_id = resp.json()["account_id"]
    person_id = resp.json()["atlas_person_id"]
    
    # Enroll biometrics artificially
    from atlas_ui.backend.routes.biometric import _face_store
    _face_store.save_templates(person_id, [[0.1]*512])

    resp_login = client.post("/api/v1/auth/login", json={"username": "del_target", "password": "pw"})
    del_sess = resp_login.json()["session_id"]

    # 9. Delete user & 10. Biometric templates removed & 11. Sessions invalidated
    assert client.delete(f"/api/v1/admin/users/{acc_id}", headers={"Authorization": f"Bearer {sess}"}).status_code == 200
    
    assert _face_store.has_templates(person_id) is False
    assert client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {del_sess}"}).status_code == 401
    
    users = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"}).json()["users"]
    assert not any(u["account_id"] == acc_id for u in users)

def test_reset_biometrics():
    sess = get_admin_session()
    resp = client.post("/api/v1/admin/users", json={
        "username": "res_target", "password": "pw", "display_name": "Res", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    person_id = resp.json()["atlas_person_id"]
    
    from atlas_ui.backend.routes.biometric import _face_store
    _face_store.save_templates(person_id, [[0.2]*512])
    
    # 12. Reset biometrics
    assert client.post(f"/api/v1/admin/people/{person_id}/reset-biometrics", headers={"Authorization": f"Bearer {sess}"}).status_code == 200
    assert _face_store.has_templates(person_id) is False
    
    users = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"}).json()["users"]
    u = next(u for u in users if u["atlas_person_id"] == person_id)
    assert u["face_enrollment_status"] == "NOT_ENROLLED"
    assert u["template_count"] == 0

def test_final_admin_safeguards():
    sess = get_admin_session()
    users = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"}).json()["users"]
    
    # First, make sure there is ONLY one admin.
    admins = [u for u in users if u["role"] == "ADMIN" and u["enabled"] == True]
    admin_acc_id = next(u["account_id"] for u in admins if u["username"] == "admin_user")
    
    # Delete or disable all other admins
    for a in admins:
        if a["account_id"] != admin_acc_id:
            client.delete(f"/api/v1/admin/users/{a['account_id']}", headers={"Authorization": f"Bearer {sess}"})
            
    # Now there is exactly 1 admin.
    # 14. Final active ADMIN cannot be disabled
    resp = client.put(f"/api/v1/admin/users/{admin_acc_id}", json={
        "username": "admin_user", "display_name": "Admin", "role": "ADMIN", "enabled": False
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp.status_code == 400
    assert "final active administrator" in resp.json()["error"]
    
    # Cannot downgrade to USER
    resp2 = client.put(f"/api/v1/admin/users/{admin_acc_id}", json={
        "username": "admin_user", "display_name": "Admin", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 400
    
    # 15. Final active ADMIN cannot be deleted
    resp3 = client.delete(f"/api/v1/admin/users/{admin_acc_id}", headers={"Authorization": f"Bearer {sess}"})
    assert resp3.status_code == 400
    assert "final active administrator" in resp3.json()["error"]

# ==============================================================================
# PHASE 3 TESTS: Password Management
# ==============================================================================

def test_change_password_other_user():
    sess = get_admin_session()
    
    # Create target user
    resp = client.post("/api/v1/admin/users", json={
        "username": "pw_target", "password": "old_password", "display_name": "Target", "role": "USER", "enabled": True
    }, headers={"Authorization": f"Bearer {sess}"})
    acc_id = resp.json()["account_id"]
    
    # Target logs in
    login_resp = client.post("/api/v1/auth/login", json={"username": "pw_target", "password": "old_password"})
    assert login_resp.status_code == 200
    target_sess = login_resp.json()["session_id"]
    
    # Admin changes target's password (current password not required)
    resp2 = client.put(f"/api/v1/admin/users/{acc_id}/password", json={
        "new_password": "new_secure_password_123!"
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 200
    assert "password_hash" not in resp2.json()
    
    # Verify target's old session is revoked
    assert client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {target_sess}"}).status_code == 401
    
    # Old password no longer works
    assert client.post("/api/v1/auth/login", json={"username": "pw_target", "password": "old_password"}).status_code == 401
    
    # New password works
    assert client.post("/api/v1/auth/login", json={"username": "pw_target", "password": "new_secure_password_123!"}).status_code == 200

def test_change_own_password():
    sess = get_admin_session()
    
    # Get admin account id
    users = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {sess}"}).json()["users"]
    admin_acc_id = next(u["account_id"] for u in users if u["username"] == ADMIN_USER)
    
    # Admin tries to change own password WITHOUT current password (fails)
    resp1 = client.put(f"/api/v1/admin/users/{admin_acc_id}/password", json={
        "new_password": "new_admin_password"
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp1.status_code == 400
    assert "Current password is required" in resp1.json()["error"]
    
    # Admin tries to change own password with WRONG current password (fails)
    resp2 = client.put(f"/api/v1/admin/users/{admin_acc_id}/password", json={
        "new_password": "new_admin_password",
        "current_password": "wrong_password"
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp2.status_code == 401, resp2.text
    assert "Incorrect current password" in resp2.json()["error"]
    
    # Admin changes own password with CORRECT current password (success)
    resp3 = client.put(f"/api/v1/admin/users/{admin_acc_id}/password", json={
        "new_password": "new_admin_password",
        "current_password": ADMIN_PASS
    }, headers={"Authorization": f"Bearer {sess}"})
    assert resp3.status_code == 200
    
    # Admin's old session is revoked
    assert client.get("/api/v1/auth/session", headers={"Authorization": f"Bearer {sess}"}).status_code == 401
    
    # Verify login with new password
    login_resp = client.post("/api/v1/auth/login", json={"username": ADMIN_USER, "password": "new_admin_password"})
    if login_resp.status_code == 401 and login_resp.json().get("biometric_required"):
        pid = login_resp.json()["person_id"]
        tok = "p6_admin_token"
        from atlas_ui.backend.main import app
        app.state.auth_service.register_biometric_success(pid, tok)
        login_resp = client.post("/api/v1/auth/login", json={
            "username": ADMIN_USER,
            "password": "new_admin_password",
            "biometric_input": tok,
        })
    assert login_resp.status_code == 200
    new_sess = login_resp.json()["session_id"]
    
    # Reset back to original to not break subsequent tests if any
    client.put(f"/api/v1/admin/users/{admin_acc_id}/password", json={
        "new_password": ADMIN_PASS,
        "current_password": "new_admin_password"
    }, headers={"Authorization": f"Bearer {new_sess}"})
