import json
import uuid
import time
from typing import Dict, Any, List, Optional
from atlas_core.memory.base import BaseKnowledgeMemory
from atlas_core.memory.store import SQLiteMemoryStore

class KnowledgeMemory(BaseKnowledgeMemory):
    def __init__(self, store: SQLiteMemoryStore):
        self.store = store

    def set_fact(self, entity_id: str, entity_type: str, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        if metadata is None:
            metadata = {}
            
        now = time.time()
        knowledge_id = str(uuid.uuid4())
        
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT knowledge_id, created_at FROM knowledge WHERE entity_id=? AND entity_type=? AND key=?", (entity_id, entity_type, key))
            row = cursor.fetchone()
            
            if row:
                cursor.execute("""
                UPDATE knowledge 
                SET value_json=?, metadata_json=?, updated_at=?
                WHERE entity_id=? AND entity_type=? AND key=?
                """, (json.dumps(value), json.dumps(metadata), now, entity_id, entity_type, key))
            else:
                cursor.execute("""
                INSERT INTO knowledge (
                    knowledge_id, entity_id, entity_type, key, value_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (knowledge_id, entity_id, entity_type, key, json.dumps(value), json.dumps(metadata), now, now))
            
            conn.commit()

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "knowledge_id": row[0],
            "entity_id": row[1],
            "entity_type": row[2],
            "key": row[3],
            "value": json.loads(row[4]),
            "metadata": json.loads(row[5]),
            "created_at": row[6],
            "updated_at": row[7]
        }

    def get_fact(self, entity_id: str, entity_type: str, key: str) -> Optional[Dict[str, Any]]:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM knowledge WHERE entity_id=? AND entity_type=? AND key=?", (entity_id, entity_type, key))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_entity_facts(self, entity_id: str, entity_type: str) -> List[Dict[str, Any]]:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM knowledge WHERE entity_id=? AND entity_type=?", (entity_id, entity_type))
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def delete_fact(self, entity_id: str, entity_type: str, key: str) -> bool:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM knowledge WHERE entity_id=? AND entity_type=? AND key=?", (entity_id, entity_type, key))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
