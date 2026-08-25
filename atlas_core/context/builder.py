from typing import Dict, Any
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.events.event import Event

class ContextBuilder:
    def __init__(self, world_state: WorldState, event_history: EventHistory, entity_extractor: EntityExtractor):
        self.world_state = world_state
        self.event_history = event_history
        self.entity_extractor = entity_extractor

    def build_context(self, trigger_event: Event) -> Dict[str, Any]:
        entities = self.entity_extractor.extract(trigger_event.payload)
        
        trigger_dict = {
            "event_id": trigger_event.event_id,
            "source": trigger_event.source,
            "event_type": trigger_event.event_type,
            "timestamp": trigger_event.timestamp,
            "priority": trigger_event.priority,
            "payload": trigger_event.payload,
            "metadata": trigger_event.metadata
        }

        world_state_dict = {
            "active_persons": list(self.world_state.active_persons),
            "active_devices": list(self.world_state.active_devices),
            "sensor_values": dict(self.world_state.sensor_values)
        }

        recent_events = []
        for ev in self.event_history.get_recent():
            if ev.event_id != trigger_event.event_id:
                recent_events.append({
                    "event_id": ev.event_id,
                    "source": ev.source,
                    "event_type": ev.event_type,
                    "timestamp": ev.timestamp,
                    "priority": ev.priority,
                    "payload": ev.payload,
                    "metadata": ev.metadata
                })

        return {
            "trigger_event": trigger_dict,
            "entities": entities,
            "world_state": world_state_dict,
            "recent_events": recent_events
        }
