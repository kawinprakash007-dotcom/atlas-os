import time
from fastapi.testclient import TestClient
from atlas_ui.backend.main import app

def print_separator(title: str):
    print("\n" + "="*70)
    print(f" {title} ")
    print("="*70)

def main():
    print("==================================================")
    print("ATLAS OS v1.8 UI & Authentication Security Demo")
    print("==================================================")

    client = TestClient(app)

    # --------------------------------------------------
    # SCENARIO 1 — Valid USER Login -> Success
    # --------------------------------------------------
    print_separator("SCENARIO 1 — Valid USER login -> Face Verified")
    
    user_payload = {
        "username": "normal_user",
        "password": "user_pass_123",
        "biometric_input": "valid_user_face"
    }

    response = client.post("/api/v1/auth/login", json=user_payload)
    print(f"HTTP Status: {response.status_code}")
    print(response.text)
    user_session_id = response.json().get("session_id")

    # --------------------------------------------------
    # SCENARIO 2 — Valid ADMIN Login -> Success
    # --------------------------------------------------
    print_separator("SCENARIO 2 — Valid ADMIN login -> Face Verified")

    admin_payload = {
        "username": "admin_user",
        "password": "admin_pass_123",
        "biometric_input": "valid_admin_face"
    }

    response = client.post("/api/v1/auth/login", json=admin_payload)
    print(f"HTTP Status: {response.status_code}")
    print(response.text)
    admin_session_id = response.json().get("session_id")

    # --------------------------------------------------
    # SCENARIO 3 — Correct Password but Face Mismatch
    # --------------------------------------------------
    print_separator("SCENARIO 3 — Password Correct but Face Mismatch")

    # Configure mock face verifier to fail for the user account explicitly
    # Get user account id first from registry
    user_acc = app.state.account_registry.get_account_by_username("normal_user")
    app.state.face_verifier.configure_account(user_acc.account_id, verified=False)

    mismatch_payload = {
        "username": "normal_user",
        "password": "user_pass_123",
        "biometric_input": "mismatch_face"
    }

    response = client.post("/api/v1/auth/login", json=mismatch_payload)
    print(f"HTTP Status: {response.status_code}")
    print(response.text)

    # Re-enable face verification for the user account for subsequent scenarios
    app.state.face_verifier.configure_account(user_acc.account_id, verified=True)

    # --------------------------------------------------
    # SCENARIO 4 — Invalid Credentials
    # --------------------------------------------------
    print_separator("SCENARIO 4 — Invalid Credentials -> Generic Error")

    invalid_payload = {
        "username": "normal_user",
        "password": "wrong_password_abc",
        "biometric_input": "face"
    }

    response = client.post("/api/v1/auth/login", json=invalid_payload)
    print(f"HTTP Status: {response.status_code}")
    print(response.text)

    # --------------------------------------------------
    # SCENARIO 5 — USER Attempts ADMIN Action -> Access Denied
    # --------------------------------------------------
    print_separator("SCENARIO 5 — USER Session Accesses Dashboard (USER vs ADMIN)")

    # Access user dashboard using user session token
    headers_user = {"Authorization": f"Bearer {user_session_id}"}
    response = client.get("/api/v1/dashboard", headers=headers_user)
    print(f"USER accessing Dashboard HTTP Status: {response.status_code}")
    print(f"Response: {response.text}")

    # Access admin controls check
    # Frontend/backend verifies that USER has no admin controls returned in response
    has_admin_controls = response.json().get("admin_controls") is not None
    print(f"Response contains admin controls? {has_admin_controls}")

    # Access admin dashboard using admin session token
    headers_admin = {"Authorization": f"Bearer {admin_session_id}"}
    response_admin = client.get("/api/v1/dashboard", headers=headers_admin)
    print(f"\nADMIN accessing Dashboard HTTP Status: {response_admin.status_code}")
    has_admin_controls_admin = response_admin.json().get("admin_controls") is not None
    print(f"Response contains admin controls? {has_admin_controls_admin}")

    # --------------------------------------------------
    # SCENARIO 6 — Logout -> Session Invalidated
    # --------------------------------------------------
    print_separator("SCENARIO 6 — Logout -> Further Access Rejected")

    # Call logout
    logout_response = client.post("/api/v1/auth/logout", headers=headers_user)
    print(f"Logout HTTP Status: {logout_response.status_code}")
    print(logout_response.text)

    # Attempt to reuse the invalidated session token
    reuse_response = client.get("/api/v1/dashboard", headers=headers_user)
    print(f"\nReusing invalidated session HTTP Status: {reuse_response.status_code}")
    print(reuse_response.text)

    print("\nDemonstration completed successfully.")

if __name__ == "__main__":
    main()
