import pytest
import os
from atlas_core.reasoning.intent_router import IntentRouter
from atlas_core.reasoning.command_reasoner import CommandReasoner
from atlas_core.reasoning.llm_service import LLMService
from atlas_core.reasoning.engine import FakeReasoner

@pytest.fixture
def intent_router():
    # Force disabled for tests so it falls back immediately
    os.environ["ATLAS_LLM_ENABLED"] = "false"
    fake = FakeReasoner()
    command_reasoner = CommandReasoner(fallback_reasoner=fake)
    llm_service = LLMService()
    return IntentRouter(command_reasoner=command_reasoner, llm_service=llm_service)

def test_intent_router_command(intent_router):
    # Supported command should bypass LLM and return OSCommandAction
    situation = {"trigger_event": {"payload": {"message": "show system information"}}}
    decision = intent_router.reason(situation, {})
    assert decision.recommended_actions[0]["action_type"] == "OSCommandAction"
    assert decision.recommended_actions[0]["payload"]["command"] == "systeminfo"

def test_intent_router_rejected(intent_router):
    # Malicious command should be rejected without hitting LLM
    situation = {"trigger_event": {"payload": {"message": "ping 8.8.8.8 & whoami"}}}
    decision = intent_router.reason(situation, {})
    assert "outside the ATLAS safety policy" in decision.decision_rationale
    assert not decision.recommended_actions

def test_intent_router_conversational_fallback(intent_router):
    # Unsupported command should be routed to LLM, which is disabled in this test, triggering fallback
    situation = {"trigger_event": {"payload": {"message": "what can you do?"}}}
    decision = intent_router.reason(situation, {})
    assert "Conversational response fallback" in decision.situation_summary
    assert "Advanced reasoning is currently unavailable" in decision.decision_rationale
    assert not decision.recommended_actions

def test_intent_router_llm_enabled():
    os.environ["ATLAS_LLM_ENABLED"] = "true"
    os.environ["ATLAS_OLLAMA_URL"] = "http://127.0.0.1:65535/invalid" # Force failure
    fake = FakeReasoner()
    command_reasoner = CommandReasoner(fallback_reasoner=fake)
    llm_service = LLMService()
    router = IntentRouter(command_reasoner=command_reasoner, llm_service=llm_service)
    
    # Simulate LLM failure by using an invalid URL
    # The LLMService will catch the connection error and return None, hitting the fallback
    situation = {"trigger_event": {"payload": {"message": "what can you do?"}}}
    decision = router.reason(situation, {})
    assert "Conversational response fallback" in decision.situation_summary
    os.environ["ATLAS_LLM_ENABLED"] = "false"
