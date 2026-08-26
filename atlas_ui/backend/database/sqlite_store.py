import sqlite3
import os
from typing import Dict, List, Any, Optional

class SQLiteStore:
    def __init__(self, db_path: str = None):
        if db_path is None:
            import sys
            if "pytest" in sys.modules:
                db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "atlas_test.db"))
                # Wipe it clean if it exists
                if os.path.exists(db_path):
                    try:
                        os.remove(db_path)
                    except:
                        pass
            else:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                db_path = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "data", "atlas.db"))
        
        self.db_path = db_path
        
        # Ensure directory exists if not in memory
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        self._init_db()
        
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if self.db_path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        return conn
        
    def _init_db(self):
        with self.get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                role TEXT NOT NULL,
                enabled BOOLEAN NOT NULL
            )
            """)
            
            conn.execute("""
            CREATE TABLE IF NOT EXISTS persons (
                person_id TEXT PRIMARY KEY,
                account_id TEXT,
                display_name TEXT NOT NULL,
                role TEXT,
                face_enrollment_status TEXT NOT NULL,
                template_count INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
            )
            """)
            conn.commit()

    # ACCOUNTS
    def create_account(self, account_id: str, username: str, password_hash: str, password_salt: str, role: str, enabled: bool):
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO accounts (account_id, username, password_hash, password_salt, role, enabled) VALUES (?, ?, ?, ?, ?, ?)",
                    (account_id, username, password_hash, password_salt, role, enabled)
                )
                conn.commit()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Username '{username}' already exists.")
            raise
            
    def update_account(self, account_id: str, username: str, role: str, enabled: bool, password_hash: str = None, password_salt: str = None):
        try:
            with self.get_connection() as conn:
                if password_hash and password_salt:
                    conn.execute(
                        "UPDATE accounts SET username=?, role=?, enabled=?, password_hash=?, password_salt=? WHERE account_id=?",
                        (username, role, enabled, password_hash, password_salt, account_id)
                    )
                else:
                    conn.execute(
                        "UPDATE accounts SET username=?, role=?, enabled=? WHERE account_id=?",
                        (username, role, enabled, account_id)
                    )
                conn.commit()
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Username '{username}' already exists.")
            raise

    def delete_account(self, account_id: str):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM accounts WHERE account_id=?", (account_id,))
            conn.commit()
            
    def get_all_accounts(self) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM accounts")
            return cur.fetchall()

    # PERSONS
    def create_person(self, person_id: str, account_id: Optional[str], display_name: str, role: Optional[str], face_enrollment_status: str, template_count: int):
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO persons (person_id, account_id, display_name, role, face_enrollment_status, template_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (person_id, account_id, display_name, role, face_enrollment_status, template_count)
                )
                conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to insert person: {e}")
            
    def update_person(self, person_id: str, account_id: Optional[str], display_name: str, role: Optional[str], face_enrollment_status: str, template_count: int):
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE persons SET account_id=?, display_name=?, role=?, face_enrollment_status=?, template_count=? WHERE person_id=?",
                    (account_id, display_name, role, face_enrollment_status, template_count, person_id)
                )
                conn.commit()
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Failed to update person: {e}")

    def delete_person(self, person_id: str):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM persons WHERE person_id=?", (person_id,))
            conn.commit()
            
    def get_all_persons(self) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            cur = conn.execute("SELECT * FROM persons")
            return cur.fetchall()
