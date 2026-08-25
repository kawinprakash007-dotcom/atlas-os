from typing import Any, Dict, List
import copy

class EvidenceCollector:
    def collect(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> List[str]:
        # Do not mutate inputs
        context_copy = copy.deepcopy(situation_context)
        memory_copy = copy.deepcopy(retrieved_memory)
        
        evidence_set = set()
        
        # Traverse Situation Context
        self._traverse(context_copy, evidence_set)
        
        # Traverse Retrieved Memory
        self._traverse(memory_copy, evidence_set)
        
        # Return sorted for deterministic ordering
        return sorted(list(evidence_set))
        
    def _traverse(self, data: Any, evidence_set: set, prefix: str = ""):
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    self._traverse(value, evidence_set, prefix)
                elif value is not None and value != "":
                    # Special handling for standard knowledge format
                    if key == "key" and "entity_id" in data and "value" in data:
                        evidence_set.add(f"{data.get('entity_id')} {value} {data.get('value')}")
                    elif key not in ["entity_id", "entity_type", "value", "knowledge_id", "created_at", "updated_at", "episode_id", "event_id", "timestamp"]:
                        evidence_set.add(f"{key} {value}")
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    self._traverse(item, evidence_set, prefix)
                elif item is not None and item != "":
                    evidence_set.add(f"{item}")
