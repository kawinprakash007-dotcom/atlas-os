import pytest
from atlas_core.reasoning.command_reasoner import CommandReasoner
from atlas_core.reasoning.engine import FakeReasoner

@pytest.fixture
def reasoner():
    fallback = FakeReasoner()
    return CommandReasoner(fallback_reasoner=fallback)

def test_system_info(reasoner):
    context = {"payload": {"message": "what is my system status"}}
    decision = reasoner.reason(context, {})
    assert decision.confidence == 1.0
    assert not decision.requires_deep_analysis
    assert "SYSTEM_INFO" in decision.inferences[0]
    assert decision.recommended_actions[0]["payload"]["command"] == "systeminfo"

def test_network_info(reasoner):
    context = {"payload": {"message": "show network information"}}
    decision = reasoner.reason(context, {})
    assert "NETWORK_INFO" in decision.inferences[0]
    assert decision.recommended_actions[0]["payload"]["command"] == "ipconfig"

def test_directory_list(reasoner):
    context = {"payload": {"message": "list files"}}
    decision = reasoner.reason(context, {})
    assert "DIRECTORY_LIST" in decision.inferences[0]
    assert decision.recommended_actions[0]["payload"]["command"] == "dir"

def test_echo(reasoner):
    context = {"payload": {"message": "say hello"}}
    decision = reasoner.reason(context, {})
    assert "ECHO" in decision.inferences[0]
    assert decision.recommended_actions[0]["payload"]["command"] == "echo Hello from ATLAS"

def test_ping_valid(reasoner):
    context = {"payload": {"message": "ping 8.8.8.8"}}
    decision = reasoner.reason(context, {})
    assert "NETWORK_TEST" in decision.inferences[0]
    assert decision.recommended_actions[0]["payload"]["command"] == "ping 8.8.8.8"

    context = {"payload": {"message": "ping google.com"}}
    decision = reasoner.reason(context, {})
    assert decision.recommended_actions[0]["payload"]["command"] == "ping google.com"

def test_ping_invalid(reasoner):
    context = {"payload": {"message": "ping 8.8.8.8; rm -rf /"}}
    decision = reasoner.reason(context, {})
    # Should trigger safety check before even reaching ping parsing due to ';'
    assert "Unsafe command syntax" in decision.situation_summary
    assert not decision.recommended_actions
    
    # What if it bypasses syntax check but has invalid chars for ping? 
    context = {"payload": {"message": "ping 8.8.8.8 xyz!"}}
    decision = reasoner.reason(context, {})
    assert "Invalid ping target" in decision.situation_summary
    assert not decision.recommended_actions

def test_unsafe_injection_shell_operators(reasoner):
    unsafe_messages = [
        "system info & dir",
        "show files | more",
        "ping 8.8.8.8 ; echo owned",
        "say hello > file.txt",
        "network status < file.txt",
        "echo test && dir",
        "echo test || dir",
        "run powershell",
        "cmd.exe /c dir"
    ]
    for msg in unsafe_messages:
        context = {"payload": {"message": msg}}
        decision = reasoner.reason(context, {})
        assert "Unsafe command syntax detected" in decision.situation_summary
        assert not decision.recommended_actions

def test_unsupported_commands(reasoner):
    context = {"payload": {"message": "launch notepad"}}
    decision = reasoner.reason(context, {})
    assert "Unsupported user request" in decision.situation_summary
    assert "not currently enabled" in decision.decision_rationale
    assert not decision.recommended_actions

def test_fallback(reasoner):
    # Empty message should trigger fallback
    context = {"payload": {"message": ""}}
    decision = reasoner.reason(context, {})
    assert decision.situation_summary == "Deterministic test situation."
