import time
import secrets
from typing import Dict, Any

from atlas_ui.backend.identity.person_registry import PersonRegistry
from atlas_ui.backend.identity.vision_identity_client import LocalVisionIdentityClient, FaceVerificationRequest
from atlas_ui.backend.identity.enrollment_service import EnrollmentService
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.sessions.session_manager import SessionManager
from atlas_ui.backend.audit.auth_audit import AuthenticationAudit
from atlas_ui.backend.services.authentication_service import AuthenticationService

def print_separator(title: str):
    print("\n" + "="*80)
    print(f" {title} ")
    print("="*80)

def main():
    print("======================================================================")
    print("ATLAS OS v1.9 Identity & Biometric Authority Layer Demonstration")
    print("======================================================================")

    # Initialize Core Security components
    account_registry = AccountRegistry()
    credential_verifier = CredentialVerifier(account_registry)
    person_registry = PersonRegistry()
    vision_client = LocalVisionIdentityClient()
    enrollment_service = EnrollmentService(person_registry, vision_client)
    session_manager = SessionManager()
    audit_log = AuthenticationAudit()
    
    auth_service = AuthenticationService(
        account_registry=account_registry,
        credential_verifier=credential_verifier,
        vision_client=vision_client,
        person_registry=person_registry,
        session_manager=session_manager,
        audit=audit_log
    )

    # Helper to seed account
    def create_mock_account(username: str, password_raw: str, role: str) -> str:
        salt = secrets.token_hex(16)
        pw_hash = credential_verifier.hash_password(password_raw, bytes.fromhex(salt)).hex()
        acc = account_registry.create_account(
            username=username,
            password_hash=pw_hash,
            password_salt=salt,
            role=role
        )
        return acc.account_id

    # Seed ADMIN and USER credentials accounts
    admin_acc_id = create_mock_account("demo_admin", "admin_pass", "ADMIN")
    user_acc_id = create_mock_account("demo_user", "user_pass", "USER")

    # --------------------------------------------------
    # SCENARIO 1 — Create USER Person
    # --------------------------------------------------
    print_separator("SCENARIO 1: Create USER Person")
    user_person = person_registry.create_person(
        display_name="Operator Jane",
        account_id=user_acc_id,
        role="USER"
    )
    print(f"User Person Created:\nID: {user_person.atlas_person_id}\nName: {user_person.display_name}\nStatus: {user_person.status}\nBiometrics: {user_person.face_enrollment_status}")

    # --------------------------------------------------
    # SCENARIO 2 — Create ADMIN Person
    # --------------------------------------------------
    print_separator("SCENARIO 2: Create ADMIN Person")
    admin_person = person_registry.create_person(
        display_name="Superuser Smith",
        account_id=admin_acc_id,
        role="ADMIN"
    )
    print(f"Admin Person Created:\nID: {admin_person.atlas_person_id}\nName: {admin_person.display_name}\nStatus: {admin_person.status}\nBiometrics: {admin_person.face_enrollment_status}")

    # --------------------------------------------------
    # SCENARIO 3 — Enroll USER biometric successfully
    # --------------------------------------------------
    print_separator("SCENARIO 3: Enroll USER Biometric Successfully")
    user_sample = "jane_face_vector_hex"
    success = enrollment_service.enroll_person_face(user_person.atlas_person_id, user_sample)
    updated_user = person_registry.get_person(user_person.atlas_person_id)
    print(f"Enrollment Success? {success}")
    print(f"New Biometric State: {updated_user.face_enrollment_status}")

    # --------------------------------------------------
    # SCENARIO 4 — Enroll ADMIN biometric successfully
    # --------------------------------------------------
    print_separator("SCENARIO 4: Enroll ADMIN Biometric Successfully")
    admin_sample = "smith_face_vector_hex"
    success = enrollment_service.enroll_person_face(admin_person.atlas_person_id, admin_sample)
    updated_admin = person_registry.get_person(admin_person.atlas_person_id)
    print(f"Enrollment Success? {success}")
    print(f"New Biometric State: {updated_admin.face_enrollment_status}")

    # --------------------------------------------------
    # SCENARIO 5 — Successful face verification
    # --------------------------------------------------
    print_separator("SCENARIO 5: Successful Face Verification")
    verify_req = FaceVerificationRequest(
        atlas_person_id=updated_user.atlas_person_id,
        biometric_raw_sample=user_sample
    )
    verify_res = vision_client.verify_face(verify_req)
    print(f"Verification call results:")
    print(f"Success: {verify_res.success}")
    print(f"Verified: {verify_res.verified}")
    print(f"Confidence: {verify_res.confidence}")

    # --------------------------------------------------
    # SCENARIO 6 — Failed face verification
    # --------------------------------------------------
    print_separator("SCENARIO 6: Failed Face Verification")
    # Simulate mismatched face (overriding the outcome)
    vision_client.configure_verification(updated_user.atlas_person_id, verified=False, confidence=0.12)
    verify_req_fail = FaceVerificationRequest(
        atlas_person_id=updated_user.atlas_person_id,
        biometric_raw_sample="stranger_face_vector"
    )
    verify_res_fail = vision_client.verify_face(verify_req_fail)
    print(f"Verification Mismatch call results:")
    print(f"Success: {verify_res_fail.success}")
    print(f"Verified: {verify_res_fail.verified}")
    print(f"Confidence: {verify_res_fail.confidence}")
    
    # Restore normal matching
    vision_client.configure_verification(updated_user.atlas_person_id, verified=True)

    # --------------------------------------------------
    # SCENARIO 7 — Authentication success (credentials + face verifier)
    # --------------------------------------------------
    print_separator("SCENARIO 7: Auth Success using Credentials + Enrolled Biometrics")
    login_res = auth_service.login("demo_user", "user_pass", user_sample)
    print(f"Authenticated? {login_res['authenticated']}")
    print(f"Granted Role: {login_res['role']}")
    print(f"Session Token: {login_res['session_id']}")

    # --------------------------------------------------
    # SCENARIO 8 — Authentication rejection when face is not enrolled
    # --------------------------------------------------
    print_separator("SCENARIO 8: Auth Rejection when Biometrics Not Enrolled")
    # Seed new account and person without enrolling
    temp_acc_id = create_mock_account("temp_user", "temp_pass", "USER")
    temp_person = person_registry.create_person(display_name="Temp Operator", account_id=temp_acc_id, role="USER")
    
    login_res_un = auth_service.login("temp_user", "temp_pass", "face_sample")
    print(f"Authenticated? {login_res_un['authenticated']}")
    print(f"Reason Message: {login_res_un['message']}")

    # --------------------------------------------------
    # SCENARIO 9 — Biometric revocation
    # --------------------------------------------------
    print_separator("SCENARIO 9: Biometric Revocation")
    revoke_success = enrollment_service.revoke_person_face(updated_user.atlas_person_id)
    revoked_user = person_registry.get_person(updated_user.atlas_person_id)
    print(f"Revocation Call Success? {revoke_success}")
    print(f"Person Status: {revoked_user.status}")
    print(f"Biometric State: {revoked_user.face_enrollment_status}")

    # --------------------------------------------------
    # SCENARIO 10 — Authentication failure after biometric revocation
    # --------------------------------------------------
    print_separator("SCENARIO 10: Auth Failure after Biometric Revocation")
    login_res_rev = auth_service.login("demo_user", "user_pass", user_sample)
    print(f"Authenticated? {login_res_rev['authenticated']}")
    print(f"Reason Message: {login_res_rev['message']}")

    print("\nDemonstration completed successfully.")

if __name__ == "__main__":
    main()
