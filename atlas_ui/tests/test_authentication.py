import os
import time
import pytest
import secrets
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from atlas_ui.backend.configuration import UIConfiguration
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.identity.person_models import Person
from atlas_ui.backend.identity.person_registry import PersonRegistry
from atlas_ui.backend.sessions.session_manager import SessionManager
from atlas_ui.backend.audit.auth_audit import AuthenticationAudit
from atlas_ui.backend.services.authentication_service import AuthenticationService
from atlas_ui.backend.main import app

@pytest.fixture
def clean_registry():
    return AccountRegistry()

@pytest.fixture
def clean_verifier(clean_registry):
    return CredentialVerifier(clean_registry)

@pytest.fixture
def clean_person_registry():
    return PersonRegistry()



@pytest.fixture
def clean_session_manager():
    return SessionManager(default_lifetime_seconds=5)

@pytest.fixture
def clean_audit():
    return AuthenticationAudit()

@pytest.fixture
def clean_service(
    clean_registry,
    clean_verifier,
    clean_person_registry,
    clean_session_manager,
    clean_audit
):
    return AuthenticationService(
        account_registry=clean_registry,
        credential_verifier=clean_verifier,
        person_registry=clean_person_registry,
        session_manager=clean_session_manager,
        audit=clean_audit
    )

@pytest.fixture
def seeded_registry(clean_registry, clean_verifier, clean_person_registry):
    # Seed ADMIN account
    admin_salt = secrets.token_hex(16)
    admin_hash = clean_verifier.hash_password("admin_pass", bytes.fromhex(admin_salt)).hex()
    admin_acc = clean_registry.create_account(
        username="admin_usr",
        password_hash=admin_hash,
        password_salt=admin_salt,
        role="ADMIN",
        enabled=True
    )
    # Link to ADMIN person and enroll face
    admin_person = clean_person_registry.create_person(
        display_name="Admin Person",
        account_id=admin_acc.account_id,
        role="ADMIN"
    )
    clean_person_registry.update_person(admin_person.atlas_person_id, face_enrollment_status="ENROLLED")

    # Seed USER account
    user_salt = secrets.token_hex(16)
    user_hash = clean_verifier.hash_password("user_pass", bytes.fromhex(user_salt)).hex()
    user_acc = clean_registry.create_account(
        username="user_usr",
        password_hash=user_hash,
        password_salt=user_salt,
        role="USER",
        enabled=True
    )
    # Link to USER person and enroll face
    user_person = clean_person_registry.create_person(
        display_name="User Person",
        account_id=user_acc.account_id,
        role="USER"
    )
    clean_person_registry.update_person(user_person.atlas_person_id, face_enrollment_status="ENROLLED")

    # Seed DISABLED account
    disabled_salt = secrets.token_hex(16)
    disabled_hash = clean_verifier.hash_password("disabled_pass", bytes.fromhex(disabled_salt)).hex()
    disabled_acc = clean_registry.create_account(
        username="disabled_usr",
        password_hash=disabled_hash,
        password_salt=disabled_salt,
        role="USER",
        enabled=False
    )
    disabled_person = clean_person_registry.create_person(
        display_name="Disabled Person",
        account_id=disabled_acc.account_id,
        role="USER"
    )
    clean_person_registry.update_person(disabled_person.atlas_person_id, face_enrollment_status="ENROLLED")
    
    return clean_registry


# 1. Valid USER login
# 2. Valid ADMIN login
def test_valid_logins(clean_service, seeded_registry, clean_person_registry):
    # Get person IDs
    user_person = clean_person_registry.get_person_by_account(seeded_registry.get_account_by_username("user_usr").account_id)
    admin_person = clean_person_registry.get_person_by_account(seeded_registry.get_account_by_username("admin_usr").account_id)

    # USER Login (Phase 1: Requires Biometric)
    res_user_1 = clean_service.login(username="user_usr", password="user_pass")
    assert res_user_1["authenticated"] is False
    assert res_user_1["biometric_required"] is True
    assert res_user_1["person_id"] == user_person.atlas_person_id

    # Simulate biometric success
    clean_service.register_biometric_success(user_person.atlas_person_id, "user_token_123")

    # USER Login (Phase 2: Finalize)
    res_user = clean_service.login(username="user_usr", password="user_pass", biometric_input="user_token_123")
    assert res_user["authenticated"] is True
    assert res_user["role"] == "USER"
    assert "VIEW_SYSTEM" in res_user["permissions"]
    assert "MANAGE_DEVICES" not in res_user["permissions"]
    assert res_user["session_id"] is not None

    # ADMIN Login (Phase 1)
    res_admin_1 = clean_service.login(username="admin_usr", password="admin_pass")
    assert res_admin_1["biometric_required"] is True
    
    clean_service.register_biometric_success(admin_person.atlas_person_id, "admin_token_123")

    # ADMIN Login (Phase 2)
    res_admin = clean_service.login(username="admin_usr", password="admin_pass", biometric_input="admin_token_123")
    assert res_admin["authenticated"] is True
    assert res_admin["role"] == "ADMIN"
    assert "MANAGE_DEVICES" in res_admin["permissions"]


# 3. Invalid username
# 4. Invalid password
# 10. Generic authentication failure messages
def test_invalid_credentials(clean_service, seeded_registry):
    # 3. Invalid username
    res = clean_service.login(username="invalid_usr", password="user_pass", biometric_input="face_data")
    assert res["authenticated"] is False
    assert res["message"] == "Authentication failed"
    assert res["role"] is None

    # 4. Invalid password
    res_pass = clean_service.login(username="user_usr", password="wrong_password", biometric_input="face_data")
    assert res_pass["authenticated"] is False
    assert res_pass["message"] == "Authentication failed"


# 5. Disabled account
def test_disabled_account_rejection(clean_service, seeded_registry):
    res = clean_service.login(username="disabled_usr", password="disabled_pass", biometric_input="face_data")
    assert res["authenticated"] is False
    assert res["message"] == "Authentication failed"


# 7. Missing username
# 8. Missing password
def test_missing_login_parameters(clean_service, seeded_registry, clean_person_registry, clean_session_manager, clean_audit):
    # Missing username
    res1 = clean_service.login(username="", password="user_pass", biometric_input="face_data")
    assert res1["authenticated"] is False

    # Missing password
    res2 = clean_service.login(username="user_usr", password="", biometric_input="face_data")
    assert res2["authenticated"] is False



# 11. Password is not stored as plaintext
# 12. Password hashes are not exposed
def test_password_hashing_and_exposure(seeded_registry):
    user = seeded_registry.get_account_by_username("user_usr")
    assert user.password_hash != "user_pass"
    assert len(user.password_hash) > 10
    
    # Verify we never return hashes in standard representations (e.g. metadata or dictionaries)
    # The account registry returns the account safely inside python, but API boundaries filter them.
    # We will test public API schemas for this in test_authorization.py


# 13. Dummy verification for unknown usernames
def test_dummy_verification_timing(clean_verifier, clean_registry):
    # To check that verify_credentials performs hash validation even for missing users
    # Mock hashlib.pbkdf2_hmac to verify it is called in both cases
    import hashlib
    original_pbkdf2 = hashlib.pbkdf2_hmac
    
    call_count = 0
    def spy_pbkdf2(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_pbkdf2(*args, **kwargs)
        
    hashlib.pbkdf2_hmac = spy_pbkdf2
    
    # 1. Verification of existing account with valid hex representations
    clean_registry.create_account(
        username="u1", 
        password_hash="0000000000000000000000000000000000000000000000000000000000000000", 
        password_salt="00000000000000000000000000000000", 
        role="USER"
    )
    try:
        clean_verifier.verify_credentials("u1", "pass")
    except ValueError:
        pass
        
    count_after_existing = call_count
    
    # 2. Verification of unknown account
    try:
        clean_verifier.verify_credentials("unknown_usr", "pass")
    except ValueError:
        pass
        
    count_after_unknown = call_count
    
    # Restore original function
    hashlib.pbkdf2_hmac = original_pbkdf2
    
    assert count_after_existing > 0
    assert count_after_unknown > count_after_existing


# 14. Successful audit logging
# 15. Failed audit logging
# Audit records do not leak sensitive information
def test_audit_logging(clean_service, seeded_registry, clean_audit, clean_person_registry):
    user_person = clean_person_registry.get_person_by_account(seeded_registry.get_account_by_username("user_usr").account_id)
    clean_service.register_biometric_success(user_person.atlas_person_id, "test_audit_token")

    # Success audit
    clean_service.login(username="user_usr", password="user_pass", biometric_input="test_audit_token")
    records = clean_audit.list_records()
    assert len(records) > 0
    
    success_rec = next(r for r in records if r.event_type == "LOGIN_SUCCESS")
    assert success_rec.access_result == "SUCCESS"
    assert success_rec.role == "USER"
    
    # Audit safety: verify no secrets stored
    for rec in records:
        assert not hasattr(rec, "password")
        assert not hasattr(rec, "password_hash")
        assert not hasattr(rec, "biometric_input")


# 16. Session creation
# 17. Session validation
# 18. Session expiration
# 19. Logout invalidates session
# 20. Session cannot be reused after logout
def test_session_lifecycle(clean_session_manager):
    # 16. Session creation
    sess = clean_session_manager.create_session("acc_1", "USER", ["VIEW_SYSTEM"])
    assert sess.session_id is not None
    assert sess.is_active is True

    # 17. Session validation
    validated = clean_session_manager.validate_session(sess.session_id)
    assert validated is not None
    assert validated.session_id == sess.session_id

    # 18. Session expiration (sleep to trigger expiry check)
    time.sleep(6) # fixture configured for 5s expiry
    expired = clean_session_manager.validate_session(sess.session_id)
    assert expired is None

    # 19. Logout invalidates session
    sess2 = clean_session_manager.create_session("acc_2", "USER", ["VIEW_SYSTEM"])
    clean_session_manager.revoke_session(sess2.session_id)
    
    # 20. Cannot be reused
    assert clean_session_manager.get_session(sess2.session_id) is None
    assert clean_session_manager.validate_session(sess2.session_id) is None


# Immutability tests
def test_immutability(clean_registry, clean_session_manager):
    # AccountRegistry deep-copy
    clean_registry.create_account("u1", "hash", "salt", "USER")
    acc = clean_registry.get_account_by_username("u1")
    acc.username = "hacked"
    
    original = clean_registry.get_account_by_username("u1")
    assert original.username == "u1"

    # SessionManager deep-copy
    sess = clean_session_manager.create_session("acc_1", "USER", ["VIEW_SYSTEM"])
    sess.permissions.append("HACK_ADMIN")
    
    validated = clean_session_manager.validate_session(sess.session_id)
    assert "HACK_ADMIN" not in validated.permissions
