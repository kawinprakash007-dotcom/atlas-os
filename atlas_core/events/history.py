from typing import List
from atlas_core.events.event import Event

class EventHistory:
    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.events: List[Event] = []

    def add_event(self, event: Event):
        self.events.append(event)
        if len(self.events) > self.max_size:
            self.events.pop(0)

    def get_recent(self, limit: int = None) -> List[Event]:
        if limit is None or limit >= len(self.events):
            return list(self.events)
        return list(self.events[-limit:])
