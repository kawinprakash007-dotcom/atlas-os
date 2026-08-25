import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.validator import DecisionValidator
from atlas_core.reasoning.qwen import ReasoningIntegrationError

class OrnithReasoner(BaseReasoner):
    def __init__(
        self, 
        model_name: str = "hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M", 
        host: str = "http://localhost:11434", 
        timeout: int = 120
    ):
        self.model_name = model_name
        self.host = host
        self.timeout = timeout
        self.validator = DecisionValidator()

    def _build_prompt(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> str:
        escalation_context = situation_context.get("escalation_context", None)
        
        # Remove escalation_context from the displayed original situation context to avoid nesting/duplication
        clean_situation_context = {k: v for k, v in situation_context.items() if k != "escalation_context"}

        prompt = (
            "You are the ATLAS Deep Reasoning Layer.\n"
            "Your job is to independently reassess the situation. The primary decision is NOT authoritative.\n"
            "You must:\n"
            "1. Identify verified observations.\n"
            "2. Separate facts from assumptions.\n"
            "3. Examine unsupported or uncertain claims from the primary reasoning.\n"
            "4. Look for contradictions.\n"
            "5. Reassess risks.\n"
            "6. Produce your own independent decision.\n"
            "7. Avoid inventing facts.\n"
            "8. Clearly express uncertainty where evidence is insufficient.\n"
            "9. Never modify world state.\n"
            "10. Never modify memory.\n"
            "11. Never execute actions.\n"
            "12. Only return a structured reasoning Decision.\n\n"
        )

        prompt += "1. ORIGINAL SITUATION CONTEXT:\n"
        prompt += json.dumps(clean_situation_context, indent=2) + "\n\n"
        
        prompt += "2. RETRIEVED MEMORY:\n"
        prompt += json.dumps(retrieved_memory, indent=2) + "\n\n"

        if escalation_context:
            prompt += "3. PRIMARY MODEL DECISION:\n"
            primary_decision = escalation_context.get("primary_decision", {})
            prompt += json.dumps(primary_decision, indent=2) + "\n\n"
            
            prompt += "4. PRIMARY GROUNDING REPORT:\n"
            primary_grounding = escalation_context.get("primary_grounding_report", {})
            prompt += json.dumps(primary_grounding, indent=2) + "\n\n"
            
            prompt += "5. REASON FOR ESCALATION:\n"
            instructions = escalation_context.get("instructions", "Requires deeper analysis.")
            prompt += instructions + "\n\n"

        prompt += """Return ONLY valid JSON in the following format:
{
  "situation_summary": "string",
  "observations": ["string"],
  "inferences": ["string"],
  "decision_rationale": "string",
  "risks": ["string"],
  "recommended_actions": [
    {
      "action_type": "string",
      "payload": {}
    }
  ],
  "confidence": 0.0,
  "requires_deep_analysis": false
}
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
