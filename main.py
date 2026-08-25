import json
import os
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder
from atlas_core.events.gateway import EventGateway
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.memory.manager import MemoryManager

def main():
    print("Initializing ATLAS Core v0.3...")
    
    # Clean up previous db if it exists for a clean run (optional, but good for demo)
    if os.path.exists("data/atlas_memory.db"):
        try:
            os.remove("data/atlas_memory.db")
        except:
            pass

    # 1. Initialize ATLAS memory database.
    store = SQLiteMemoryStore("data/atlas_memory.db")
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    memory_manager = MemoryManager(episodic, knowledge)

    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)
    
    gateway = EventGateway(world, history, builder, memory_manager)
    
    # 2. Process events
    events_to_process = [
        Event(
            source="vision_system", 
            event_type="person_entered", 
            priority="normal", 
            payload={"person_id": "person_001", "camera_id": "lab_cam"}
        ),
        Event(
            source="smart_home", 
            event_type="device_activated", 
            priority="normal", 
            payload={"device_id": "device_lab_01"}
        ),
        Event(
            source="thermometer", 
            event_type="sensor_updated", 
            priority="low", 
            payload={"sensor_id": "lab_temp", "value": 23.5}
        )
    ]
    
    final_context = None
    for event in events_to_process:
        print(f"\nProcessing event: {event.event_type} from {event.source}")
        final_context = gateway.process(event)
        
    # 3. Show the final Situation Context.
    print("\nFinal Situation Context:")
    if final_context:
        print(json.dumps(final_context, indent=2))
    else:
        print("No context returned.")

    # 4. Retrieve and print the history for: person_001
    print("\nRetrieving history for person_001:")
    history_p1 = memory_manager.recall_entity_history("person_001")
    print(json.dumps(history_p1, indent=2))

    # 5. Store this fact
    print("\nStoring fact for device_lab_01...")
    memory_manager.remember_fact(
        entity_id="device_lab_01",
        entity_type="device",
        key="normal_temperature_range",
        value={"min": 30, "max": 45}
    )

    # 6. Retrieve and print this fact
    print("\nRetrieving fact for device_lab_01:")
    fact = memory_manager.recall_fact("device_lab_01", "device", "normal_temperature_range")
    print(json.dumps(fact, indent=2))

if __name__ == "__main__":
    main()
