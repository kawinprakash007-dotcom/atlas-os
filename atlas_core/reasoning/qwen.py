import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.validator import DecisionValidator

class ReasoningIntegrationError(Exception):
    def __init__(self, phase: str, message: str, original_error: Optional[Exception] = None):
        super().__init__(f"[{phase}] {message}")
        self.phase = phase
        self.message = message
        self.original_error = original_error

class QwenReasoner(BaseReasoner):
    def __init__(self, model_name: str = "qwen3:8b", host: str = "http://localhost:11434", timeout: int = 60):
        self.model_name = model_name
        self.host = host
        self.timeout = timeout
        self.validator = DecisionValidator()

    def _build_prompt(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> str:
        prompt = f"""
You are the Reasoning Engine for ATLAS Core.
Your role is to analyze the situation context and retrieved memory to make a decision.
Do not invent events or facts.
Clearly distinguish observations from inferences.
Risks must be supported by the available context.
Recommended actions are proposals only. Do not claim that actions were executed.
Do not directly modify ATLAS state or memory.
If evidence is insufficient, state uncertainty and set requires_deep_analysis to true.

Situation Context:
{json.dumps(situation_context, indent=2)}

Retrieved Memory:
{json.dumps(retrieved_memory, indent=2)}

Return ONLY valid JSON in the following format:
{{
  "situation_summary": "string",
  "observations": ["string"],
  "inferences": ["string"],
  "decision_rationale": "string",
  "risks": ["string"],
  "recommended_actions": [
    {{
      "action_type": "string",
      "payload": {{}}
    }}
  ],
  "confidence": 0.0,
  "requires_deep_analysis": false
}}
"""
        return prompt

    def reason(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> Decision:
        prompt = self._build_prompt(situation_context, retrieved_memory)

        data = {
            "model": self.model_name,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2
            }
        }
        
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            response = urllib.request.urlopen(req, timeout=self.timeout)
            response_body = response.read().decode("utf-8")
        except urllib.error.URLError as e:
            if isinstance(e.reason, TimeoutError) or "timeout" in str(e.reason).lower():
                raise ReasoningIntegrationError("ollama_connection", "Connection timed out", e)
            raise ReasoningIntegrationError("ollama_connection", f"Failed to connect to Ollama: {str(e)}", e)
        except Exception as e:
            raise ReasoningIntegrationError("ollama_connection", f"Unexpected connection error: {str(e)}", e)

        try:
            response_json = json.loads(response_body)
            if "response" not in response_json:
                raise ReasoningIntegrationError("model_generation", "Ollama response missing 'response' field")
            raw_decision_text = response_json["response"]
        except json.JSONDecodeError as e:
            raise ReasoningIntegrationError("model_generation", "Ollama API returned invalid JSON", e)

        try:
            decision_data = json.loads(raw_decision_text)
        except json.JSONDecodeError as e:
            raise ReasoningIntegrationError("json_parsing", "Model output is not valid JSON", e)

        # Decision Construction
        try:
            decision = Decision(
                situation_summary=decision_data.get("situation_summary", ""),
                observations=decision_data.get("observations", []),
                inferences=decision_data.get("inferences", []),
                decision_rationale=decision_data.get("decision_rationale", ""),
                risks=decision_data.get("risks", []),
                recommended_actions=decision_data.get("recommended_actions", []),
                confidence=float(decision_data.get("confidence", 0.0)),
                requires_deep_analysis=bool(decision_data.get("requires_deep_analysis", False))
            )
        except Exception as e:
            raise ReasoningIntegrationError("decision_construction", f"Failed to construct Decision object: {str(e)}", e)

        # Validation
        validation_result = self.validator.validate(decision)
        if not validation_result["is_valid"]:
            error_msgs = "; ".join(validation_result["errors"])
            raise ReasoningIntegrationError("decision_validation", f"Decision validation failed: {error_msgs}")

        return decision
