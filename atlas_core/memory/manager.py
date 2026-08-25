from typing import Dict, Any, List, Optional
from atlas_core.events.event import Event
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory

class MemoryManager:
    def __init__(self, episodic_memory: EpisodicMemory, knowledge_memory: KnowledgeMemory):
        self.episodic_memory = episodic_memory
        self.knowledge_memory = knowledge_memory

    def remember_event(self, event: Event, entities: Dict[str, List[str]]):
        return self.episodic_memory.store_event(event, entities)

    def remember_fact(self, entity_id: str, entity_type: str, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        self.knowledge_memory.set_fact(entity_id, entity_type, key, value, metadata)

    def recall_entity_history(self, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.episodic_memory.get_by_entity(entity_id, limit)

    def recall_fact(self, entity_id: str, entity_type: str, key: str) -> Optional[Dict[str, Any]]:
        return self.knowledge_memory.get_fact(entity_id, entity_type, key)

    def recall_entity_facts(self, entity_id: str, entity_type: str) -> List[Dict[str, Any]]:
        return self.knowledge_memory.get_entity_facts(entity_id, entity_type)
