import json
import urllib.request
import urllib.error
import pytest
from unittest.mock import patch, MagicMock

from atlas_core.reasoning.ornith import OrnithReasoner
from atlas_core.reasoning.qwen import ReasoningIntegrationError
from atlas_core.reasoning.decision import Decision

@pytest.fixture
def ornith():
    return OrnithReasoner()

@pytest.fixture
def sample_context():
    return {"entities": {"device_id": ["device_01"]}, "state": "offline"}

@pytest.fixture
def sample_memory():
    return {"relevant_knowledge": {"device_01": [{"key": "status", "value": "offline"}]}}

@pytest.fixture
def valid_json_response():
    return {
        "response": json.dumps({
            "situation_summary": "Device is offline.",
            "observations": ["device_01 is offline"],
            "inferences": ["device may need repair"],
            "decision_rationale": "Given the offline status, maintenance is required.",
            "risks": ["data loss"],
            "recommended_actions": [{"action_type": "dispatch_technician", "payload": {}}],
            "confidence": 0.8,
            "requires_deep_analysis": False
        })
    }

def test_successful_ollama_response(ornith, sample_context, sample_memory, valid_json_response):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(valid_json_response).encode("utf-8")
        mock_urlopen.return_value = mock_response

        decision = ornith.reason(sample_context, sample_memory)

        assert isinstance(decision, Decision)
        assert decision.situation_summary == "Device is offline."
        assert len(decision.observations) == 1
        assert decision.confidence == 0.8

def test_ollama_connection_failure(ornith, sample_context, sample_memory):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with pytest.raises(ReasoningIntegrationError) as exc_info:
            ornith.reason(sample_context, sample_memory)

        assert exc_info.value.phase == "ollama_connection"

def test_invalid_json_rejected(ornith, sample_context, sample_memory):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"NOT JSON"
        mock_urlopen.return_value = mock_response

        with pytest.raises(ReasoningIntegrationError) as exc_info:
            ornith.reason(sample_context, sample_memory)

        assert exc_info.value.phase == "model_generation"

def test_missing_response_field(ornith, sample_context, sample_memory):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        # Missing "response" key
        mock_response.read.return_value = json.dumps({"other_field": "data"}).encode("utf-8")
        mock_urlopen.return_value = mock_response

        with pytest.raises(ReasoningIntegrationError) as exc_info:
            ornith.reason(sample_context, sample_memory)

        assert exc_info.value.phase == "model_generation"
        assert "missing 'response' field" in str(exc_info.value)

def test_structurally_invalid_decision_json_rejected(ornith, sample_context, sample_memory):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        # "response" contains invalid JSON string
        mock_response.read.return_value = json.dumps({"response": "NOT A JSON OBJECT"}).encode("utf-8")
        mock_urlopen.return_value = mock_response

        with pytest.raises(ReasoningIntegrationError) as exc_info:
            ornith.reason(sample_context, sample_memory)

        assert exc_info.value.phase == "json_parsing"

def test_decision_validation_failure(ornith, sample_context, sample_memory):
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        # Missing required field like 'observations' (Decision class allows empty, but validation fails if not list?)
        # Wait, Decision dataclass has defaults, but DecisionValidator checks things.
        # Let's provide an invalid type for confidence.
        invalid_decision = {
            "situation_summary": "",
            "observations": "NOT A LIST", # Invalid type
            "inferences": [],
            "decision_rationale": "",
            "risks": [],
            "recommended_actions": [],
            "confidence": 2.0, # Out of range (0.0 to 1.0)
            "requires_deep_analysis": False
        }
        mock_response.read.return_value = json.dumps({"response": json.dumps(invalid_decision)}).encode("utf-8")
        mock_urlopen.return_value = mock_response

        with pytest.raises(ReasoningIntegrationError) as exc_info:
            ornith.reason(sample_context, sample_memory)
            
        assert exc_info.value.phase == "decision_validation" or exc_info.value.phase == "decision_construction"

def test_escalation_context_prompt_generation(ornith, sample_context, sample_memory):
    # This is the MOST IMPORTANT test.
    
    escalation_context = {
        "instructions": "Requires deeper analysis.",
        "primary_decision": {"situation_summary": "Primary summary"},
        "primary_grounding_report": {"status": "REQUIRES_DEEP_ANALYSIS"}
    }
    
    situation_with_escalation = sample_context.copy()
    situation_with_escalation["escalation_context"] = escalation_context

    prompt = ornith._build_prompt(situation_with_escalation, sample_memory)
    
    # 1. Original situation context should not contain the nested escalation_context
    assert "escalation_context" not in prompt.split("2. RETRIEVED MEMORY:")[0]
    
    # 2. It must contain the primary decision
    assert "3. PRIMARY MODEL DECISION:" in prompt
    assert "Primary summary" in prompt
    
    # 3. It must contain the grounding report
    assert "4. PRIMARY GROUNDING REPORT:" in prompt
    assert "REQUIRES_DEEP_ANALYSIS" in prompt
    
    # 4. It must contain the reason for escalation
    assert "5. REASON FOR ESCALATION:" in prompt
    assert "Requires deeper analysis." in prompt
