import pytest
from atlas_core.events.event import Event

def test_event_creation():
    event = Event(
        source="test_source",
        event_type="test_type",
        priority="normal",
        payload={"key": "value"}
    )
    assert event.source == "test_source"
    assert event.event_type == "test_type"
    assert event.priority == "normal"
    assert event.payload == {"key": "value"}
    assert event.event_id is not None
    assert event.timestamp is not None

def test_event_validation_invalid_priority():
    with pytest.raises(ValueError, match="Invalid priority"):
        Event(source="s", event_type="t", priority="invalid", payload={})

def test_event_validation_missing_source():
    with pytest.raises(ValueError):
        Event(source="", event_type="t", priority="normal", payload={})

def test_event_validation_missing_type():
    with pytest.raises(ValueError):
        Event(source="s", event_type="", priority="normal", payload={})
