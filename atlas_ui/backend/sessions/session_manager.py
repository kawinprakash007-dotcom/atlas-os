import time
import copy
import secrets
from typing import Dict, Optional, List
from atlas_ui.backend.models.session import Session

class SessionManager:
    def __init__(self, default_lifetime_seconds: float = 3600.0):
        self.default_lifetime_seconds = default_lifetime_seconds
        # Maps token -> Session object
        self._sessions: Dict[str, Session] = {}

    def create_session(
        self,
        account_id: str,
        role: str,
        permissions: List[str],
        lifetime_seconds: Optional[float] = None
    ) -> Session:
        session_id = secrets.token_hex(32)
        now = time.time()
        expiry = now + (lifetime_seconds if lifetime_seconds is not None else self.default_lifetime_seconds)
        
        sess = Session(
            session_id=session_id,
            account_id=account_id,
            role=role,
            created_at=now,
            expires_at=expiry,
            last_activity=now,
            is_active=True,
            permissions=copy.deepcopy(permissions)
        )
        self._sessions[session_id] = sess
        return copy.deepcopy(sess)

    def get_session(self, session_id: str) -> Optional[Session]:
        # Perform lazy cleanup check
        sess = self._sessions.get(session_id)
        if sess is None:
            return None
        
        # Check active status and expiration
        if not sess.is_active or time.time() > sess.expires_at:
            sess.is_active = False
            self.revoke_session(session_id)
            return None
            
        return copy.deepcopy(sess)

    def validate_session(self, session_id: str) -> Optional[Session]:
        sess = self.get_session(session_id)
        if sess is None:
            return None
        
        # Update last activity in internal state
        internal_sess = self._sessions[session_id]
        internal_sess.last_activity = time.time()
        
        return copy.deepcopy(internal_sess)

    def revoke_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def list_active_sessions(self) -> List[Session]:
        now = time.time()
        active = []
        for sid, sess in list(self._sessions.items()):
            if sess.is_active and now <= sess.expires_at:
                active.append(copy.deepcopy(sess))
            else:
                self._sessions.pop(sid, None)
        return active
