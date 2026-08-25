from typing import Dict, Any, List, Optional
from atlas_core.memory.manager import MemoryManager

class MemoryRetriever:
    """
    Safely retrieves relevant context from the MemoryManager.
    Strictly read-only to prevent state mutation during the reasoning phase.
    """
    def __init__(self, memory_manager: MemoryManager):
        self.memory_manager = memory_manager

    def retrieve(self, situation_context: Dict[str, Any], entity_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Retrieves episodic and knowledge memory relevant to the situation context.
        """
        relevant_episodes = []
        relevant_knowledge = {}

        # Simple deterministic mapping
        entity_mapping = {
            "person_id": "person",
            "device_id": "device",
            "sensor_id": "sensor"
        }

        if situation_context and "entities" in situation_context:
            for key, ids in situation_context["entities"].items():
                entity_type = entity_mapping.get(key)
                for entity_id in ids:
                    # 1. Fetch Episodes
                    episodes = self.memory_manager.recall_entity_history(entity_id, limit=5)
                    if episodes:
                        relevant_episodes.extend(episodes)
                    
                    # 2. Fetch Knowledge if we know the type
                    if entity_type:
                        facts = self.memory_manager.recall_entity_facts(entity_id, entity_type)
                        if facts:
                            if entity_id not in relevant_knowledge:
                                relevant_knowledge[entity_id] = []
                            relevant_knowledge[entity_id].extend(facts)

        return {
            "relevant_episodes": relevant_episodes,
            "relevant_knowledge": relevant_knowledge
        }
