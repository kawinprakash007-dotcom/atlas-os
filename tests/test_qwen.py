import json
import pytest
from unittest.mock import patch, MagicMock
import urllib.error

from atlas_core.reasoning.qwen import QwenReasoner, ReasoningIntegrationError
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import BaseReasoner

def test_qwen_reasoner_implements_interface():
    reasoner = QwenReasoner()
    assert isinstance(reasoner, BaseReasoner)

@patch("urllib.request.urlopen")
def test_successful_qwen_response(mock_urlopen):
    # Mocking successful API response
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "response": json.dumps({
            "situation_summary": "Test Summary",
            "observations": ["Obs 1"],
            "inferences": ["Inf 1"],
            "decision_rationale": "Rationale 1",
            "risks": ["Risk 1"],
            "recommended_actions": [{"action_type": "move", "payload": {}}],
            "confidence": 0.9,
            "requires_deep_analysis": False
        })
    }).encode("utf-8")
    mock_urlopen.return_value = mock_response

    reasoner = QwenReasoner()
    decision = reasoner.reason({}, {})

    assert isinstance(decision, Decision)
    assert decision.situation_summary == "Test Summary"
    assert decision.confidence == 0.9

@patch("urllib.request.urlopen")
def test_ollama_connection_failure(mock_urlopen):
    mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
    
    reasoner = QwenReasoner()
    with pytest.raises(ReasoningIntegrationError) as exc:
        reasoner.reason({}, {})
        
    assert exc.value.phase == "ollama_connection"

@patch("urllib.request.urlopen")
def test_invalid_json_response(mock_urlopen):
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "response": "This is not JSON"
    }).encode("utf-8")
    mock_urlopen.return_value = mock_response

    reasoner = QwenReasoner()
    with pytest.raises(ReasoningIntegrationError) as exc:
        reasoner.reason({}, {})
        
    assert exc.value.phase == "json_parsing"

@patch("urllib.request.urlopen")
def test_structurally_invalid_decision_json(mock_urlopen):
    mock_response = MagicMock()
    # Semantically invalid but syntactically valid JSON
    mock_response.read.return_value = json.dumps({
        "response": json.dumps({
            "situation_summary": "Test Summary",
            "observations": "Should be a list", # Wrong type
            "inferences": [],
            "decision_rationale": "Rationale",
            "risks": [],
            "recommended_actions": [{"wrong_key": "val"}], # Malformed action
            "confidence": 2.5, # Invalid confidence value
            "requires_deep_analysis": False
        })
    }).encode("utf-8")
    mock_urlopen.return_value = mock_response

    reasoner = QwenReasoner()
    with pytest.raises(ReasoningIntegrationError) as exc:
        reasoner.reason({}, {})
        
    assert exc.value.phase == "decision_validation"
    assert "must be between 0.0 and 1.0" in exc.value.message
    assert "must be a list" in exc.value.message
    assert "non-empty string 'action_type'" in exc.value.message

@patch("urllib.request.urlopen")
def test_decision_construction_failure(mock_urlopen):
    mock_response = MagicMock()
    # Missing required fields or wrong types that break construction (like confidence being a list)
    mock_response.read.return_value = json.dumps({
        "response": json.dumps({
            "confidence": ["Not a float"]
        })
    }).encode("utf-8")
    mock_urlopen.return_value = mock_response

    reasoner = QwenReasoner()
    with pytest.raises(ReasoningIntegrationError) as exc:
        reasoner.reason({}, {})
        
    assert exc.value.phase == "decision_construction"
