import time
from typing import Dict, Any, Optional
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.identity.credential_verifier import CredentialVerifier
from atlas_ui.backend.identity.person_registry import PersonRegistry
from atlas_ui.backend.sessions.session_manager import SessionManager
from atlas_ui.backend.audit.auth_audit import AuthenticationAudit
from atlas_ui.backend.authorization.permissions import get_permissions_for_role

class AuthenticationService:
    def __init__(
        self,
        account_registry: AccountRegistry,
        credential_verifier: CredentialVerifier,
        face_verifier: Optional[Any] = None,
        person_registry: Optional[PersonRegistry] = None,
        session_manager: Optional[SessionManager] = None,
        audit: Optional[AuthenticationAudit] = None,
        vision_client: Optional[Any] = None
    ):
        self.account_registry = account_registry
        self.credential_verifier = credential_verifier
        self.person_registry = person_registry
        self.session_manager = session_manager
        self.audit = audit
        self.face_verifier = face_verifier

    def login(
        self,
        username: Optional[str],
        password: Optional[str],
        biometric_input: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        gps_latitude: Optional[float] = None,
        gps_longitude: Optional[float] = None,
        gps_accuracy: Optional[float] = None,
        location_permission: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes secure credentials-only login flow:
        1. Validate input structural limits.
        2. Verify credentials and account enabled check.
        3. Create session, write audit, return result.
        """
        # 1. Structural Validation
        if not username or not password:
            if self.audit:
                self.audit.log_attempt(
                    event_type="LOGIN_FAILED",
                    account_id=None,
                    credential_verified=False,
                    face_verified=False,
                    access_result="FAILURE",
                    failure_category="STRUCTURAL_VALIDATION_FAILED",
                    username=username or None,
                    ip_address=ip_address,
                    device_info=user_agent,
                    gps_latitude=gps_latitude,
                    gps_longitude=gps_longitude,
                    gps_accuracy=gps_accuracy,
                )
            return {
                "authenticated": False,
                "role": None,
                "permissions": [],
                "session_id": None,
                "expires_at": None,
                "message": "Authentication failed"
            }

        # Lookup account metadata safely
        acc = self.account_registry.get_account_by_username(username)
        account_id = acc.account_id if acc else None
        print(f"[LOGIN] Username lookup: username={username}, resolved_account_id={account_id}, enabled={acc.enabled if acc else 'None'}", flush=True)

        # 2. Verify Credentials & Enabled status
        try:
            verified_acc = self.credential_verifier.verify_credentials(username, password)
            print(f"[LOGIN] Credentials validated: account_id={verified_acc.account_id}, role={verified_acc.role}", flush=True)
        except ValueError as e:
            category = "INVALID_CREDENTIALS"
            if acc and not acc.enabled:
                category = "ACCOUNT_DISABLED"

            print(f"[LOGIN] Credentials validation failed: {e} (category: {category})", flush=True)
            if self.audit:
                self.audit.log_attempt(
                    event_type="LOGIN_FAILED",
                    account_id=account_id,
                    credential_verified=False,
                    face_verified=False,
                    access_result="FAILURE",
                    failure_category=category,
                    username=username,
                    ip_address=ip_address,
                    device_info=user_agent,
                    gps_latitude=gps_latitude,
                    gps_longitude=gps_longitude,
                    gps_accuracy=gps_accuracy,
                )
            # Record failed attempt on person profile
            if self.person_registry and account_id:
                person = self.person_registry.get_person_by_account(account_id)
                if person:
                    now = time.time()
                    new_attempts = person.failed_login_attempts + 1
                    sec_event = {
                        "event": "LOGIN_FAILURE",
                        "category": category,
                        "timestamp": now,
                        "ip": ip_address,
                        "gps_latitude": gps_latitude,
                        "gps_longitude": gps_longitude,
                        "gps_accuracy": gps_accuracy,
                        "location_permission": location_permission,
                    }
                    recent = (person.recent_security_events or [])[-49:] + [sec_event]
                    self.person_registry.update_person(
                        person.atlas_person_id,
                        failed_login_attempts=new_attempts,
                        last_failed_login=now,
                        recent_security_events=recent,
                    )
            return {
                "authenticated": False,
                "role": None,
                "permissions": [],
                "session_id": None,
                "expires_at": None,
                "message": "Authentication failed"
            }

        # 3. Resolve Role and Permissions
        role = verified_acc.role
        permissions = get_permissions_for_role(role)

        # Biometric Check Phase
        person = None
        if self.person_registry:
            person = self.person_registry.get_person_by_account(verified_acc.account_id)

        # Check if biometric validation is required and if the token is valid
        if person and person.face_enrollment_status == "PENDING":
            if self.audit:
                self.audit.log_attempt(
                    event_type="LOGIN_FAILED",
                    account_id=verified_acc.account_id,
                    access_result="FAILURE",
                    failure_category="BIOMETRIC_PENDING",
                    username=username,
                    person_id=person.atlas_person_id if person else None,
                    ip_address=ip_address,
                    device_info=user_agent,
                    gps_latitude=gps_latitude,
                    gps_longitude=gps_longitude,
                    gps_accuracy=gps_accuracy,
                )
            return {
                "authenticated": False,
                "biometric_required": False,
                "role": None,
                "permissions": [],
                "session_id": None,
                "expires_at": None,
                "message": "Biometric enrollment pending. Please see an administrator."
            }

        if person and person.face_enrollment_status == "ENROLLED":
            if not biometric_input or not self._validate_biometric_token(person.atlas_person_id, biometric_input):
                return {
                    "authenticated": False,
                    "biometric_required": True,
                    "person_id": person.atlas_person_id,
                    "role": None,
                    "permissions": [],
                    "session_id": None,
                    "expires_at": None,
                    "message": "Biometric verification required"
                }

        # 4. Create Session
        if self.session_manager:
            session = self.session_manager.create_session(
                account_id=verified_acc.account_id,
                role=role,
                permissions=permissions
            )
            session_id = session.session_id
            expires_at = session.expires_at
        else:
            session_id = None
            expires_at = None

        # 5. Log success
        if self.audit:
            self.audit.log_attempt(
                event_type="LOGIN_SUCCESS",
                account_id=verified_acc.account_id,
                credential_verified=True,
                face_verified=True if (person and person.face_enrollment_status == "ENROLLED") else False,
                access_result="SUCCESS",
                role=role,
                person_id=person.atlas_person_id if person else None,
                username=username,
                session_id=session_id,
                ip_address=ip_address,
                device_info=user_agent,
                gps_latitude=gps_latitude,
                gps_longitude=gps_longitude,
                gps_accuracy=gps_accuracy,
            )

        # 6. Record login stats on Person profile
        if person and self.person_registry:
            now = time.time()
            updates: Dict[str, Any] = {
                "last_login": now,
                "login_count": person.login_count + 1,
                "failed_login_attempts": 0,           # reset on successful login
                "last_access_timestamp": now,
                "last_access_ip": ip_address,
                "last_access_device": user_agent,
                # GPS — stored only when actually captured; None leaves existing value unchanged
                "gps_latitude": gps_latitude,
                "gps_longitude": gps_longitude,
                "gps_accuracy": gps_accuracy,
                "location_permission": location_permission,
            }
            if person.first_login is None:
                updates["first_login"] = now
            self.person_registry.update_person(person.atlas_person_id, **updates)

        return {
            "authenticated": True,
            "biometric_required": False,
            "person_id": person.atlas_person_id if person else None,
            "role": role,
            "permissions": permissions,
            "session_id": session_id,
            "expires_at": expires_at,
            "message": "Authentication successful"
        }

    def _validate_biometric_token(self, person_id: str, token: str) -> bool:
        """Validates a one-time biometric token and consumes it."""
        if not hasattr(self, "_biometric_cache"):
            return False
            
        entry = self._biometric_cache.get(person_id)
        if not entry:
            return False
            
        cached_token, expiry = entry
        if time.time() > expiry or token != cached_token:
            return False
            
        # Consume the token
        del self._biometric_cache[person_id]
        return True

    def register_biometric_success(self, person_id: str, token: str, valid_for_seconds: float = 60.0):
        """Registers a temporary secure token to finalize authentication."""
        if not hasattr(self, "_biometric_cache"):
            self._biometric_cache = {}
        self._biometric_cache[person_id] = (token, time.time() + valid_for_seconds)

    def logout(self, session_id: str) -> None:
        if self.session_manager:
            sess = self.session_manager.get_session(session_id)
            if sess:
                if self.audit:
                    self.audit.log_attempt(
                        event_type="LOGOUT",
                        account_id=sess.account_id,
                        credential_verified=True,
                        face_verified=True,
                        access_result="SUCCESS",
                        role=sess.role
                    )
                # Record logout stats on Person profile
                if self.person_registry:
                    person = self.person_registry.get_person_by_account(sess.account_id)
                    if person:
                        now = time.time()
                        duration = now - sess.created_at
                        self.person_registry.update_person(
                            person.atlas_person_id,
                            last_logout=now,
                            total_session_duration=person.total_session_duration + duration,
                        )
                self.session_manager.revoke_session(session_id)
