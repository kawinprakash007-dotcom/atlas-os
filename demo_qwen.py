import json
import sys
from atlas_core.reasoning.qwen import QwenReasoner, ReasoningIntegrationError
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.memory.manager import MemoryManager
from atlas_core.reasoning.retriever import MemoryRetriever
from atlas_core.events.event import Event

def main():
    print("Initializing ATLAS Core v0.5 Qwen3 Demo...")
    
    import tempfile
    import os
    
    # 1. Initialize Mock Memory with a valid file-based DB instead of :memory:
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    
    store = SQLiteMemoryStore(db_path)
    episodic = EpisodicMemory(store)
    knowledge = KnowledgeMemory(store)
    memory_manager = MemoryManager(episodic, knowledge)
    
    # Pre-populate some facts
    memory_manager.remember_fact("device_01", "device", "location", "Main Lab")
    memory_manager.remember_fact("device_01", "device", "status", "offline")
    
    # Pre-populate an episode
    e = Event(source="door_sensor", event_type="unauthorized_entry", priority="high", payload={"person": "unknown"})
    memory_manager.remember_event(e, {"device_id": ["device_01"]})
    
    retriever = MemoryRetriever(memory_manager)
    
    # 2. Simulate Situation Context
    situation_context = {
        "event_type": "motion_detected",
        "timestamp": 1692800000.0,
        "entities": {
            "device_id": ["device_01"]
        },
        "payload": {
            "camera_feed": "motion at 3am"
        }
    }
    
    print("\nRetrieving Memory...")
    retrieved_memory = retriever.retrieve(situation_context)
    
    # 3. Initialize QwenReasoner
    # Note: Requires Ollama to be running locally with qwen3:8b installed
    reasoner = QwenReasoner(model_name="qwen3:8b", host="http://localhost:11434", timeout=60)
    
    print("\nSending data to QwenReasoner...")
    try:
        decision = reasoner.reason(situation_context, retrieved_memory)
        print("\n=== Validated Decision ===")
        print(json.dumps(decision.to_dict(), indent=2))
        
    except ReasoningIntegrationError as e:
        print(f"\n[ERROR] Integration Failed in phase '{e.phase}':")
        print(f"Message: {e.message}")
        if e.original_error:
            print(f"Original Error: {e.original_error}")
        print("\nPlease ensure Ollama is running and 'qwen3:8b' is pulled.")
        sys.exit(1)
    finally:
        # Cleanup
        try:
            os.remove(db_path)
        except OSError:
            pass

if __name__ == "__main__":
    main()
