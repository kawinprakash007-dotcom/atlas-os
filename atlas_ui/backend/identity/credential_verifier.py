import hmac
import hashlib
from typing import Optional
from atlas_ui.backend.identity.account_registry import AccountRegistry
from atlas_ui.backend.models.account import Account

class CredentialVerifier:
    def __init__(self, account_registry: AccountRegistry):
        self.account_registry = account_registry
        
        # Pre-calculated dummy salt and hash to run timing checks for invalid users
        # Salt size: 16 bytes (hex), hash size: 32 bytes (hex)
        self._dummy_salt = "d3b07384d113edec49eaa6238ad5ff00"
        self._dummy_hash = "f1a1d1c1b1a10101f2a2d2c2b2a20202f3a3d3c3b3a30303f4a4d4c4b4a40404"

    @staticmethod
    def hash_password(password: str, salt: bytes, iterations: int = 100000) -> bytes:
        """
        Derives key using PBKDF2-HMAC-SHA256.
        """
        return hashlib.pbkdf2_hmac(
            hash_name='sha256',
            password=password.encode('utf-8'),
            salt=salt,
            iterations=iterations
        )

    def verify_credentials(self, username: str, password: str) -> Account:
        """
        Verifies credentials, raising a generic ValueError on failure.
        Prevents username enumeration using dummy timing loops.
        """
        acc = self.account_registry.get_account_by_username(username)
        
        if acc is not None:
            # Active account verification
            salt_bytes = bytes.fromhex(acc.password_salt)
            expected_hash = bytes.fromhex(acc.password_hash)
            
            calculated_hash = self.hash_password(password, salt_bytes)
            
            # Constant-time comparison
            is_valid = hmac.compare_digest(calculated_hash, expected_hash)
            
            if not is_valid:
                raise ValueError("Authentication failed")
                
            if not acc.enabled:
                raise ValueError("Authentication failed")
                
            return acc
        else:
            # Run dummy verification to hide timing differences
            dummy_salt_bytes = bytes.fromhex(self._dummy_salt)
            dummy_expected_hash = bytes.fromhex(self._dummy_hash)
            
            calculated_dummy = self.hash_password(password, dummy_salt_bytes)
            # Constant-time compare anyway
            hmac.compare_digest(calculated_dummy, dummy_expected_hash)
            
            raise ValueError("Authentication failed")
