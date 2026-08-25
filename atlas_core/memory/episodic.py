import json
import uuid
import time
from typing import Dict, Any, List, Optional
from atlas_core.events.event import Event
from atlas_core.memory.base import BaseEpisodicMemory
from atlas_core.memory.store import SQLiteMemoryStore

class EpisodicMemory(BaseEpisodicMemory):
    def __init__(self, store: SQLiteMemoryStore):
        self.store = store

    def store_event(self, event: Event, entities: Dict[str, List[str]]) -> str:
        episode_id = str(uuid.uuid4())
        created_at = time.time()
        
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO episodes (
                episode_id, event_id, source, event_type, timestamp, priority,
                payload_json, metadata_json, entities_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode_id,
                event.event_id,
                event.source,
                event.event_type,
                event.timestamp,
                event.priority,
                json.dumps(event.payload),
                json.dumps(event.metadata),
                json.dumps(entities),
                created_at
            ))
            conn.commit()
            
        return episode_id

    def _row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "episode_id": row[0],
            "event_id": row[1],
            "source": row[2],
            "event_type": row[3],
            "timestamp": row[4],
            "priority": row[5],
            "payload": json.loads(row[6]),
            "metadata": json.loads(row[7]),
            "entities": json.loads(row[8]),
            "created_at": row[9]
        }

    def get_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_by_event_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE event_id = ?", (event_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_by_entity(self, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        search_term = f'%"{entity_id}"%'
        with self.store.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM episodes WHERE entities_json LIKE ? ORDER BY timestamp DESC LIMIT ?", (search_term, limit))
            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]
