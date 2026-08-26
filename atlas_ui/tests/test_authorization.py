import time
import pytest
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app

@pytest.fixture
def api_client():
    return TestClient(app)

from unittest.mock import patch

# Helper to get session ID for a role
def get_session_for(client: TestClient, role: str) -> str:
    username = "admin_user" if role == "ADMIN" else "normal_user"
    password = "admin_pass_123" if role == "ADMIN" else "user_pass_123"
    
    response = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password
    })
    data = response.json()
    if data.get("biometric_required"):
        person_id = data["person_id"]
        token = "test_verify_token"
        app.state.auth_service.register_biometric_success(person_id, token)
        response = client.post("/api/v1/auth/login", json={
            "username": username,
            "password": password,
            "biometric_input": token
        })
        data = response.json()
    return data["session_id"]


# 21. USER can access allowed permissions
# 22. USER cannot access ADMIN permissions
# 23. ADMIN can access all allowed permissions
def test_role_based_permissions():
    from atlas_ui.backend.authorization.access_controller import AccessController
    from atlas_ui.backend.authorization import roles, permissions

    controller = AccessController()
    
    # User permissions checks
    assert controller.has_permission(roles.USER, permissions.VIEW_SYSTEM) is True
    assert controller.has_permission(roles.USER, permissions.VIEW_DEVICES) is True
    
    # User denied admin permissions
    assert controller.has_permission(roles.USER, permissions.MANAGE_USERS) is False
    assert controller.has_permission(roles.USER, permissions.REGISTER_FACE) is False
    
    # Admin checks
    assert controller.has_permission(roles.ADMIN, permissions.VIEW_SYSTEM) is True
    assert controller.has_permission(roles.ADMIN, permissions.MANAGE_USERS) is True
    assert controller.has_permission(roles.ADMIN, permissions.REGISTER_FACE) is True


# 24. Unauthorized backend access is rejected
def test_unauthorized_endpoints(api_client):
    # Try accessing dashboard without headers
    response = api_client.get("/api/v1/dashboard")
    assert response.status_code == 401
    assert "Access denied" in response.json()["error"]


# 25. Protected endpoints validate sessions
def test_protected_endpoints_validate_session(api_client):
    # Log in as USER
    token = get_session_for(api_client, "USER")

    # Access dashboard with correct credentials
    response = api_client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "USER"
    assert data["admin_controls"] is None

    # Access dashboard with invalid token
    response_invalid = api_client.get("/api/v1/dashboard", headers={"Authorization": "Bearer invalid_token"})
    assert response_invalid.status_code == 401


# 26. Expired sessions cannot access protected resources
def test_expired_session_blocked(api_client):
    # Log in
    token = get_session_for(api_client, "USER")
    
    # Artificially expire session directly in session manager
    sess = app.state.session_manager.get_session(token)
    assert sess is not None
    
    # Update expires_at to past time
    app.state.session_manager._sessions[token].expires_at = time.time() - 100.0

    # Request dashboard
    response = api_client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "Session has expired" in response.json()["error"]


# API exposure safety checks
def test_api_security_leakage(api_client):
    # Inspect login response parameters
    username = "normal_user"
    password = "user_pass_123"
    
    response = api_client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
        "biometric_input": "mock_face"
    })
    
    data = response.json()
    assert "password_hash" not in data
    assert "password_salt" not in data
    assert "biometric_template" not in data
    assert "biometric_embedding" not in data
