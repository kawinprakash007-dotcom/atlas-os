import pytest
import os
import tempfile
from atlas_core.memory.store import SQLiteMemoryStore
from atlas_core.memory.episodic import EpisodicMemory
from atlas_core.memory.knowledge import KnowledgeMemory
from atlas_core.memory.manager import MemoryManager
from atlas_core.events.event import Event
from atlas_core.world.state import WorldState
from atlas_core.events.history import EventHistory
from atlas_core.context.entities import EntityExtractor
from atlas_core.context.builder import ContextBuilder
from atlas_core.events.gateway import EventGateway

@pytest.fixture
def memory_store():
    # Use a temporary file to avoid the per-connection :memory: isolation issue
    fd, path = tempfile.mkstemp()
    os.close(fd)
    store = SQLiteMemoryStore(path)
    yield store
    # Cleanup
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception:
            pass # Windows lock

def test_episodic_memory_stores_and_retrieves(memory_store):
    ep = EpisodicMemory(memory_store)
    e1 = Event(source="src", event_type="type1", priority="normal", payload={"key": "val"})
    ep.store_event(e1, {"person_id": ["p1"]})
    
    retrieved = ep.get_by_event_id(e1.event_id)
    assert retrieved is not None
    assert retrieved["event_type"] == "type1"
    assert retrieved["entities"] == {"person_id": ["p1"]}
    assert retrieved["payload"] == {"key": "val"}

def test_episodic_memory_recent_and_entity(memory_store):
    ep = EpisodicMemory(memory_store)
    e1 = Event(source="src", event_type="type1", priority="normal", payload={})
    e2 = Event(source="src", event_type="type2", priority="normal", payload={})
    
    ep.store_event(e1, {"person_id": ["p1"]})
    ep.store_event(e2, {"person_id": ["p2"]})
    
    recent = ep.get_recent(limit=10)
    assert len(recent) == 2
    
    by_entity = ep.get_by_entity("p1")
    assert len(by_entity) == 1
    assert by_entity[0]["event_id"] == e1.event_id

def test_knowledge_memory_stores_and_updates(memory_store):
    km = KnowledgeMemory(memory_store)
    km.set_fact("e1", "device", "status", "active")
    fact = km.get_fact("e1", "device", "status")
    assert fact["value"] == "active"
    
    # Update fact
    km.set_fact("e1", "device", "status", "inactive")
    fact_updated = km.get_fact("e1", "device", "status")
    assert fact_updated["value"] == "inactive"
    
    # Delete fact
    km.delete_fact("e1", "device", "status")
    assert km.get_fact("e1", "device", "status") is None

def test_memory_manager(memory_store):
    mm = MemoryManager(EpisodicMemory(memory_store), KnowledgeMemory(memory_store))
    e = Event(source="src", event_type="t", priority="normal", payload={})
    mm.remember_event(e, {"dev_id": ["d1"]})
    
    hist = mm.recall_entity_history("d1")
    assert len(hist) == 1
    assert hist[0]["event_id"] == e.event_id
    
    mm.remember_fact("d1", "device", "type", "sensor")
    fact = mm.recall_fact("d1", "device", "type")
    assert fact["value"] == "sensor"
    
    facts = mm.recall_entity_facts("d1", "device")
    assert len(facts) == 1
    assert facts[0]["key"] == "type"

def test_integration_with_gateway(memory_store):
    world = WorldState()
    history = EventHistory()
    extractor = EntityExtractor()
    builder = ContextBuilder(world, history, extractor)
    mm = MemoryManager(EpisodicMemory(memory_store), KnowledgeMemory(memory_store))
    
    gateway = EventGateway(world, history, builder, mm)
    
    e = Event(source="src", event_type="t", priority="normal", payload={"device_id": "d123"})
    ctx = gateway.process(e)
    
    assert ctx is not None
    assert "d123" in ctx["entities"]["device_id"]
    
    episodes = mm.recall_entity_history("d123")
    assert len(episodes) == 1
    assert episodes[0]["event_id"] == e.event_id
