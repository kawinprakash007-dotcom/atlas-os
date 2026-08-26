import pytest
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app

@pytest.fixture
def client():
    # Provide a test client
    return TestClient(app)

@pytest.fixture
def auth_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin_user", "password": "admin_pass_123"})
    if resp.status_code == 401 and resp.json().get("biometric_required"):
        pid = resp.json()["person_id"]
        tok = "p6_admin_token"
        app.state.auth_service.register_biometric_success(pid, tok)
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin_user",
            "password": "admin_pass_123",
            "biometric_input": tok,
        })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token") or resp.json().get("session_id")
    return {"Authorization": f"Bearer {token}"}

def test_im3_lifecycle_sync(client, auth_headers):
    identity_memory = app.state.identity_memory
    
    # 1. CREATE USER
    create_resp = client.post(
        "/api/v1/admin/users",
        headers=auth_headers,
        json={
            "username": "im3_sync_user",
            "password": "Password123",
            "display_name": "Sync Test",
            "role": "USER",
            "enabled": True
        }
    )
    assert create_resp.status_code == 200
    account_id = create_resp.json()["account_id"]
    person_id = create_resp.json()["atlas_person_id"]
    
    identity = identity_memory.get_identity(person_id)
    assert identity is not None
    assert identity.display_name == "Sync Test"
    assert identity.role == "USER"
    assert identity.enabled is True
    assert identity.face_enrolled is False
    
    # 2. EDIT USER (Change display_name/role)
    edit_resp = client.put(
        f"/api/v1/admin/users/{account_id}",
        headers=auth_headers,
        json={
            "username": "im3_sync_user",
            "display_name": "Sync Test Updated",
            "role": "ADMIN",
            "enabled": True
        }
    )
    assert edit_resp.status_code == 200
    
    identity = identity_memory.get_identity(person_id)
    assert identity.display_name == "Sync Test Updated"
    assert identity.role == "ADMIN"
    assert identity.enabled is True
    
    # 3. DISABLE USER
    disable_resp = client.put(
        f"/api/v1/admin/users/{account_id}",
        headers=auth_headers,
        json={
            "username": "im3_sync_user",
            "display_name": "Sync Test Updated",
            "role": "ADMIN",
            "enabled": False
        }
    )
    assert disable_resp.status_code == 200
    
    identity = identity_memory.get_identity(person_id)
    assert identity is not None
    assert identity.enabled is False
    
    vision_reg = identity_memory.get_vision_registry()
    assert not any(r["person_id"] == person_id for r in vision_reg)
    
    # 4. ENABLE USER
    enable_resp = client.put(
        f"/api/v1/admin/users/{account_id}",
        headers=auth_headers,
        json={
            "username": "im3_sync_user",
            "display_name": "Sync Test Updated",
            "role": "ADMIN",
            "enabled": True
        }
    )
    assert enable_resp.status_code == 200
    
    identity = identity_memory.get_identity(person_id)
    assert identity.enabled is True
    
    # We artificially set face_enrolled=True to test vision registry inclusion
    identity_memory.mark_face_enrolled(person_id)
    vision_reg = identity_memory.get_vision_registry()
    assert any(r["person_id"] == person_id for r in vision_reg)
    
    # 5/6. BIOMETRIC RESET
    reset_resp = client.post(
        f"/api/v1/admin/people/{person_id}/reset-biometrics",
        headers=auth_headers
    )
    assert reset_resp.status_code == 200
    
    identity = identity_memory.get_identity(person_id)
    assert identity.face_enrolled is False
    
    vision_reg = identity_memory.get_vision_registry()
    assert not any(r["person_id"] == person_id for r in vision_reg)
    
    # 7. USER DELETION
    del_resp = client.delete(
        f"/api/v1/admin/users/{account_id}",
        headers=auth_headers
    )
    assert del_resp.status_code == 200
    
    assert identity_memory.get_identity(person_id) is None
    
def test_admin_safeguards(client, auth_headers):
    # 8. ADMIN SAFEGUARDS
    # Try to delete the final active admin
    admin_person_id = "ATLAS-P-88888888"
    admin_account_id = None
    
    # Need to find the account_id for the admin user
    acc_reg = app.state.account_registry
    for acc in acc_reg.list_accounts():
        if acc.username == "admin_user":
            admin_account_id = acc.account_id
            break
            
    assert admin_account_id is not None
    
    # Delete should fail
    del_resp = client.delete(
        f"/api/v1/admin/users/{admin_account_id}",
        headers=auth_headers
    )
    assert del_resp.status_code == 400
    
    # IdentityMemory must NOT have deleted the admin
    identity_memory = app.state.identity_memory
    assert identity_memory.get_identity(admin_person_id) is not None
