import os
import requests
from typing import Dict, Any, Optional

from atlas_core.reasoning.decision import Decision
from atlas_core.reasoning.engine import BaseReasoner


class LLMService(BaseReasoner):
    """
    Local LLM reasoning service for ATLAS OS.

    This service is conversation-only.
    It does NOT execute OS commands or interact with
    the ActionExecutor.
    """

    def __init__(self):
        # Enable / disable local LLM
        self.enabled = (
            os.environ.get("ATLAS_LLM_ENABLED", "true")
            .strip()
            .lower()
            == "true"
        )

        # Provider configuration
        self.provider = os.environ.get(
            "ATLAS_LLM_PROVIDER",
            "ollama"
        ).strip().lower()

        # IMPORTANT:
        # qwen3:8b exists on your system.
        self.model = os.environ.get(
            "ATLAS_LLM_MODEL",
            "qwen3:8b"
        ).strip()

        # Ollama API endpoint
        self.base_url = os.environ.get(
            "ATLAS_OLLAMA_URL",
            "http://127.0.0.1:11434/api/generate"
        ).strip()

        # Configurable timeout
        self.timeout = float(
            os.environ.get(
                "ATLAS_LLM_TIMEOUT",
                "15"
            )
        )

        self.system_prompt = """
You are ATLAS, the intelligent conversational assistant of ATLAS OS.

Your personality is:
- Concise
- Helpful
- Intelligent
- Professional
- Futuristic
- Calm and slightly inspired by a cinematic AI assistant

You are part of ATLAS OS.

IMPORTANT SECURITY RULES:

1. You are a conversational reasoning layer only.
2. You cannot directly execute operating system commands.
3. You cannot bypass ATLAS OS security.
4. You cannot modify authentication, biometrics, users,
   permissions, or system configuration.
5. If a user asks for an action outside the secure ATLAS
   command interface, explain briefly that it is not available
   through the current secure interface.
6. Never pretend that you executed an action.
7. Do not expose internal implementation details unless asked.

RESPONSE STYLE:

- Speak naturally.
- Be concise.
- Do not mention being a language model.
- Do not say "As an AI".
- Do not generate JSON.
- Do not include markdown unless necessary.
- Answer as ATLAS.

You may discuss ATLAS OS capabilities and explain concepts,
but only the secure command engine can execute supported
system actions.
""".strip()

    def _extract_message(
        self,
        situation_context: Dict[str, Any]
    ) -> str:
        """
        Extract the user message from both production
        and test context structures.
        """

        trigger_event = situation_context.get(
            "trigger_event",
            {}
        )

        payload = trigger_event.get(
            "payload",
            situation_context.get(
                "payload",
                {}
            )
        )

        return payload.get(
            "message",
            ""
        ).strip()

    def reason(
        self,
        situation_context: Dict[str, Any],
        retrieved_memory: Dict[str, Any]
    ) -> Optional[Decision]:

        # Local LLM disabled
        if not self.enabled:
            return None

        # Currently only Ollama is supported
        if self.provider != "ollama":
            return None

        # Extract user message
        message = self._extract_message(
            situation_context
        )

        if not message:
            return None

        try:
            # Use Ollama generate API
            response = requests.post(
                self.base_url,
                json={
                    "model": self.model,

                    "prompt": (
                        f"{self.system_prompt}\n\n"
                        f"User: {message}\n"
                        f"ATLAS:"
                    ),

                    "stream": False,

                    "options": {
                        "temperature": 0.7,
                        "num_predict": 300
                    }
                },

                timeout=self.timeout
            )

            response.raise_for_status()

            data = response.json()

            llm_text = (
                data.get("response", "")
                .strip()
            )

            # Ollama returned an empty response
            if not llm_text:
                return None

            # Return conversational decision
            return Decision(
                situation_summary=(
                    "Conversational response generated."
                ),

                observations=[
                    f"User message: {message}"
                ],

                inferences=[
                    "Processed by local Ollama LLM."
                ],

                risks=[],

                recommended_actions=[],

                confidence=0.95,

                requires_deep_analysis=False,

                decision_rationale=llm_text
            )

        except requests.exceptions.Timeout:
            print(
                f"[ATLAS LLM] Request timed out "
                f"after {self.timeout} seconds."
            )
            return None

        except requests.exceptions.ConnectionError:
            print(
                "[ATLAS LLM] Cannot connect to Ollama. "
                "Make sure Ollama is running."
            )
            return None

        except requests.exceptions.HTTPError as error:
            print(
                f"[ATLAS LLM] Ollama HTTP error: "
                f"{error}"
            )
            return None

        except Exception as error:
            print(
                f"[ATLAS LLM] Unexpected error: "
                f"{error}"
            )
            return None