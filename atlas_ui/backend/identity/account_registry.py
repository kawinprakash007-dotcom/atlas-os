import uuid
import time
import copy
from typing import Dict, List, Optional
from atlas_ui.backend.models.account import Account

class AccountRegistry:
    def __init__(self, sqlite_store=None):
        self._accounts: Dict[str, Account] = {}
        self._store = sqlite_store

    def create_account(
        self,
        username: str,
        password_hash: str,
        password_salt: str,
        role: str,
        enabled: bool = True,
        metadata: Optional[dict] = None
    ) -> Account:
        # Prevent duplicate username check (case insensitive)
        for existing in self._accounts.values():
            if existing.username.lower() == username.lower():
                raise ValueError(f"Username '{username}' already exists.")

        account_id = str(uuid.uuid4())
        
        # Write to SQLite first
        if self._store:
            self._store.create_account(account_id, username, password_hash, password_salt, role, enabled)
            
        acc = Account(
            account_id=account_id,
            username=username,
            password_hash=password_hash,
            password_salt=password_salt,
            role=role,
            enabled=enabled,
            created_at=time.time(),
            metadata=dict(metadata) if metadata is not None else {}
        )
        self._accounts[account_id] = acc
        return copy.deepcopy(acc)

    def get_account(self, account_id: str) -> Optional[Account]:
        acc = self._accounts.get(account_id)
        if acc is None:
            return None
        return copy.deepcopy(acc)

    def get_account_by_username(self, username: str) -> Optional[Account]:
        for acc in self._accounts.values():
            if acc.username.lower() == username.lower():
                return copy.deepcopy(acc)
        return None

    def update_account(self, account_id: str, **kwargs) -> Account:
        if account_id not in self._accounts:
            raise KeyError(f"Account '{account_id}' does not exist.")
        acc = self._accounts[account_id]
        
        # Verify unique username if updating username
        new_username = kwargs.get("username")
        if new_username and new_username.lower() != acc.username.lower():
            for existing in self._accounts.values():
                if existing.account_id != account_id and existing.username.lower() == new_username.lower():
                    raise ValueError(f"Username '{new_username}' already exists.")

        # Determine fields for SQLite
        upd_username = new_username or acc.username
        upd_role = kwargs.get("role", acc.role)
        upd_enabled = kwargs.get("enabled", acc.enabled)
        upd_hash = kwargs.get("password_hash")
        upd_salt = kwargs.get("password_salt")

        # Write to SQLite first
        if self._store:
            self._store.update_account(account_id, upd_username, upd_role, upd_enabled, upd_hash, upd_salt)

        for k, v in kwargs.items():
            if hasattr(acc, k):
                setattr(acc, k, v)
        return copy.deepcopy(acc)

    def disable_account(self, account_id: str) -> Account:
        return self.update_account(account_id, enabled=False)

    def list_accounts(self) -> List[Account]:
        return [copy.deepcopy(acc) for acc in self._accounts.values()]

    def remove_account(self, account_id: str) -> None:
        if account_id not in self._accounts:
            raise KeyError(f"Account '{account_id}' does not exist.")
            
        if self._store:
            self._store.delete_account(account_id)
            
        self._accounts.pop(account_id)
