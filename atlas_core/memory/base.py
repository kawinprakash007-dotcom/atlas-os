from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from atlas_core.events.event import Event

class BaseEpisodicMemory(ABC):
    @abstractmethod
    def store_event(self, event: Event, entities: Dict[str, List[str]]) -> str:
        pass

    @abstractmethod
    def get_episode(self, episode_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_event_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_by_entity(self, entity_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        pass

class BaseKnowledgeMemory(ABC):
    @abstractmethod
    def set_fact(self, entity_id: str, entity_type: str, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        pass

    @abstractmethod
    def get_fact(self, entity_id: str, entity_type: str, key: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def get_entity_facts(self, entity_id: str, entity_type: str) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def delete_fact(self, entity_id: str, entity_type: str, key: str) -> bool:
        pass
