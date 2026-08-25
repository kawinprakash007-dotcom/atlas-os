import pytest
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder

def test_context_builder_builds_correctly():
    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)
    
    # Populate history
    past_event = Event(source="s1", event_type="past", priority="low", payload={})
    history.add_event(past_event)
    
    # Populate world state
    world.active_persons.add("person_xyz")
    
    # Trigger event
    trigger_event = Event(
        source="s2",
        event_type="current",
        priority="high",
        payload={"person_id": "person_xyz", "device_id": "dev_123"}
    )
    
    # It's important to simulate the fact that trigger_event is already in history,
    # as per integration rules, to ensure it doesn't get duplicated in recent_events.
    history.add_event(trigger_event)
    
    context = builder.build_context(trigger_event)
    
    # Check trigger event
    assert "trigger_event" in context
    assert context["trigger_event"]["event_id"] == trigger_event.event_id
    
    # Check world state
    assert "world_state" in context
    assert "person_xyz" in context["world_state"]["active_persons"]
    
    # Check entities
    assert "entities" in context
    assert context["entities"]["person_id"] == ["person_xyz"]
    assert context["entities"]["device_id"] == ["dev_123"]
    
    # Check recent events
    assert "recent_events" in context
    assert len(context["recent_events"]) == 1
    assert context["recent_events"][0]["event_id"] == past_event.event_id
