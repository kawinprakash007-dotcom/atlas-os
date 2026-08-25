import pytest
from atlas_core.events.history import EventHistory
from atlas_core.events.event import Event

def test_event_history_stores_events():
    history = EventHistory(max_size=5)
    e1 = Event(source="s", event_type="t", priority="normal", payload={})
    history.add_event(e1)
    
    assert len(history.events) == 1
    assert history.events[0] == e1

def test_event_history_respects_max_size():
    history = EventHistory(max_size=2)
    e1 = Event(source="s", event_type="t", priority="normal", payload={"id": 1})
    e2 = Event(source="s", event_type="t", priority="normal", payload={"id": 2})
    e3 = Event(source="s", event_type="t", priority="normal", payload={"id": 3})
    
    history.add_event(e1)
    history.add_event(e2)
    history.add_event(e3)
    
    assert len(history.events) == 2
    assert history.events[0] == e2
    assert history.events[1] == e3

def test_event_history_get_recent():
    history = EventHistory(max_size=10)
    for i in range(5):
        history.add_event(Event(source="s", event_type="t", priority="normal", payload={"id": i}))
        
    recent_3 = history.get_recent(limit=3)
    assert len(recent_3) == 3
    assert recent_3[0].payload["id"] == 2
    assert recent_3[2].payload["id"] == 4
