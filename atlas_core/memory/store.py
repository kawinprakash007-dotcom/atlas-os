import sqlite3
import os

class SQLiteMemoryStore:
    def __init__(self, db_path: str = "data/atlas_memory.db"):
        self.db_path = db_path
        self._ensure_dir()
        self._init_db()

    def _ensure_dir(self):
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                episode_id TEXT PRIMARY KEY,
                event_id TEXT UNIQUE,
                source TEXT,
                event_type TEXT,
                timestamp REAL,
                priority TEXT,
                payload_json TEXT,
                metadata_json TEXT,
                entities_json TEXT,
                created_at REAL
            )
            """)
            
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                knowledge_id TEXT PRIMARY KEY,
                entity_id TEXT,
                entity_type TEXT,
                key TEXT,
                value_json TEXT,
                metadata_json TEXT,
                created_at REAL,
                updated_at REAL,
                UNIQUE(entity_id, entity_type, key)
            )
            """)
            
            conn.commit()

    def get_connection(self):
        return sqlite3.connect(self.db_path)
