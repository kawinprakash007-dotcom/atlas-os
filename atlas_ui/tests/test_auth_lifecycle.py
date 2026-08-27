import pytest
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app, seed_mock_accounts
from atlas_ui.backend.database.sqlite_store import SQLiteStore
import os

@pytest.fixture
def client():
    # Make sure mock accounts are seeded
    seed_mock_accounts()
    return TestClient(app)

# TEST 1: Valid admin_user/admin_pass_123 returns HTTP 200
def test_valid_login_returns_200(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123"
    })
    assert response.status_code == 200

# TEST 2: authenticated == true
def test_valid_login_authenticated_true(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123"
    })
    data = response.json()
    assert data["authenticated"] is True

# TEST 3: session_id exists
def test_valid_login_session_id_exists(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123"
    })
    data = response.json()
    assert "session_id" in data
    assert data["session_id"] is not None

# TEST 4: role == ADMIN
def test_valid_login_role_admin(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123"
    })
    data = response.json()
    assert data["role"] == "ADMIN"

# TEST 5: Invalid password returns HTTP 401
def test_invalid_password_returns_401(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "wrong_password"
    })
    assert response.status_code == 401
    data = response.json()
    assert data["authenticated"] is False

# TEST 6: Unknown username returns HTTP 401
def test_unknown_username_returns_401(client):
    response = client.post("/api/v1/auth/login", json={
        "username": "non_existent_user",
        "password": "some_password"
    })
    assert response.status_code == 401
    data = response.json()
    assert data["authenticated"] is False

# TEST 7: Disabled account is rejected appropriately
def test_disabled_account_is_rejected(client):
    # Disable normal_user temporarily to test
    from atlas_ui.backend.main import account_registry
    user_acc = account_registry.get_account_by_username("normal_user")
    assert user_acc is not None
    
    # Save original status
    original_enabled = user_acc.enabled
    account_registry.update_account(user_acc.account_id, enabled=False)
    
    try:
        response = client.post("/api/v1/auth/login", json={
            "username": "normal_user",
            "password": "user_pass_123"
        })
        assert response.status_code == 401
        data = response.json()
        assert data["authenticated"] is False
    finally:
        # Restore status
        account_registry.update_account(user_acc.account_id, enabled=original_enabled)

# TEST 8: Authenticated session can access /api/v1/os/status
def test_authenticated_session_can_access_os_status(client):
    # Log in
    login_res = client.post("/api/v1/auth/login", json={
        "username": "admin_user",
        "password": "admin_pass_123"
    })
    token = login_res.json()["session_id"]
    
    # Request os status
    response = client.get("/api/v1/os/status", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "os" in data
    assert data["os"]["status"] == "healthy"

# TEST 9: Unauthenticated request to protected route is rejected
def test_unauthenticated_request_rejected(client):
    response = client.get("/api/v1/os/status")
    assert response.status_code == 401

# TEST 10: Restarting the backend does not accidentally delete or corrupt the bootstrap administrator account
def test_bootstrap_idempotency_on_restart():
    # Calling seed_mock_accounts multiple times must verify and preserve or repair admin_user
    from atlas_ui.backend.main import account_registry
    
    # First seed
    seed_mock_accounts()
    admin_acc_1 = account_registry.get_account_by_username("admin_user")
    assert admin_acc_1 is not None
    
    # Modify display name or do something else, then run seed again
    seed_mock_accounts()
    admin_acc_2 = account_registry.get_account_by_username("admin_user")
    assert admin_acc_2 is not None
    assert admin_acc_2.account_id == admin_acc_1.account_id
