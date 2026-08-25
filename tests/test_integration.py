import pytest
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder
from atlas_core.events.gateway import EventGateway

def test_gateway_integration():
    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)
    gateway = EventGateway(world, history, builder)
    
    event = Event(
        source="vision",
        event_type="person_entered",
        priority="normal",
        payload={"person_id": "p_001"}
    )
    
    context = gateway.process(event)
    
    assert context is not None
    # Context reflects updated world state
    assert "p_001" in context["world_state"]["active_persons"]
    # Trigger event is present
    assert context["trigger_event"]["event_id"] == event.event_id
    # History contains the event
    assert len(history.events) == 1
    # Recent events doesn't duplicate the trigger event
    assert len(context["recent_events"]) == 0
