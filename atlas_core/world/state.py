import copy
from typing import Set, Dict, Any, List
from atlas_core.events.event import Event

class WorldState:
    def __init__(self):
        self.active_persons: Set[str] = set()
        self.active_devices: Set[str] = set()
        self.sensor_values: Dict[str, Any] = {}
        self.recent_events: List[Event] = []
        self.action_executions: List[Dict[str, Any]] = []
        self.last_execution_batch: Dict[str, Any] = None

    def process_event(self, event: Event):
        self.recent_events.append(event)
        
        if len(self.recent_events) > 100:
            self.recent_events.pop(0)

        if event.event_type == "person_entered":
            person_id = event.payload.get("person_id")
            if person_id:
                self.active_persons.add(person_id)
        elif event.event_type == "person_left":
            person_id = event.payload.get("person_id")
            if person_id and person_id in self.active_persons:
                self.active_persons.remove(person_id)
        elif event.event_type == "device_activated":
            device_id = event.payload.get("device_id")
            if device_id:
                self.active_devices.add(device_id)
        elif event.event_type == "device_deactivated":
            device_id = event.payload.get("device_id")
            if device_id and device_id in self.active_devices:
                self.active_devices.remove(device_id)
        elif event.event_type == "sensor_updated":
            sensor_id = event.payload.get("sensor_id")
            value = event.payload.get("value")
            if sensor_id and value is not None:
                self.sensor_values[sensor_id] = value

    def record_execution_batch(self, batch_data: dict):
        safe_batch = copy.deepcopy(batch_data)
        self.action_executions.append(safe_batch)
        self.last_execution_batch = safe_batch
        
        if len(self.action_executions) > 100:
            self.action_executions.pop(0)

    def __str__(self):
        return (f"WorldState(Persons: {len(self.active_persons)}, "
                f"Devices: {len(self.active_devices)}, "
                f"Sensors: {len(self.sensor_values)})")
