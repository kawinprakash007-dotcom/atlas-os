import pytest
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.gateway import EventGateway

def test_person_entered():
    world = WorldState()
    gateway = EventGateway(world)
    event = Event(
        source="vision",
        event_type="person_entered",
        priority="normal",
        payload={"person_id": "p1"}
    )
    gateway.process(event)
    assert "p1" in world.active_persons

def test_person_left():
    world = WorldState()
    gateway = EventGateway(world)
    event1 = Event(source="v", event_type="person_entered", priority="normal", payload={"person_id": "p1"})
    event2 = Event(source="v", event_type="person_left", priority="normal", payload={"person_id": "p1"})
    
    gateway.process(event1)
    assert "p1" in world.active_persons
    
    gateway.process(event2)
    assert "p1" not in world.active_persons

def test_device_activated_deactivated():
    world = WorldState()
    gateway = EventGateway(world)
    
    gateway.process(Event(source="s", event_type="device_activated", priority="normal", payload={"device_id": "d1"}))
    assert "d1" in world.active_devices
    
    gateway.process(Event(source="s", event_type="device_deactivated", priority="normal", payload={"device_id": "d1"}))
    assert "d1" not in world.active_devices

def test_sensor_updated():
    world = WorldState()
    gateway = EventGateway(world)
    
    gateway.process(Event(source="s", event_type="sensor_updated", priority="normal", payload={"sensor_id": "temp1", "value": 22.5}))
    assert world.sensor_values["temp1"] == 22.5
