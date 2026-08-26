import re
from typing import Dict, Any
from atlas_core.reasoning.engine import BaseReasoner
from atlas_core.reasoning.decision import Decision

class CommandReasoner(BaseReasoner):
    def __init__(self, fallback_reasoner: BaseReasoner):
        self.fallback_reasoner = fallback_reasoner
        # Reject shell operators and chaining
        self.unsafe_pattern = re.compile(r'(&|\||;|>|<|&&|\|\||powershell|cmd\.exe)', re.IGNORECASE)

    def reason(self, situation_context: Dict[str, Any], retrieved_memory: Dict[str, Any]) -> Decision:
        trigger_event = situation_context.get("trigger_event", {})
        payload = trigger_event.get("payload", situation_context.get("payload", {}))
        message = payload.get("message", "").strip()
        
        # If no message, fallback
        if not message:
            return self.fallback_reasoner.reason(situation_context, retrieved_memory)

        # 1. Security Check
        if self.unsafe_pattern.search(message):
            return Decision(
                situation_summary="Unsafe command syntax detected.",
                observations=[f"User input contains forbidden shell operators: {message}"],
                inferences=["Input violates ATLAS safety policy."],
                risks=["Command injection attempt."],
                recommended_actions=[],
                confidence=1.0,
                requires_deep_analysis=False,
                decision_rationale="That command cannot be executed because it is outside the ATLAS safety policy."
            )

        msg_lower = message.lower()
        intent = None
        action_payload = None

        # 2. Intent Detection
        if msg_lower in ["system info", "show system information", "what is my system status"]:
            intent = "SYSTEM_INFO"
            action_payload = {"command": "systeminfo"}
        elif msg_lower in ["show network information", "network status", "show my ip"]:
            intent = "NETWORK_INFO"
            action_payload = {"command": "ipconfig"}
        elif msg_lower in ["list files", "show files"]:
            intent = "DIRECTORY_LIST"
            action_payload = {"command": "dir"}
        elif msg_lower in ["say hello", "echo atlas online"]:
            intent = "ECHO"
            # Extract just the safe parts or use hardcoded for these specific strings
            action_payload = {"command": "echo Hello from ATLAS"} if msg_lower == "say hello" else {"command": "echo ATLAS online"}
        elif msg_lower.startswith("ping "):
            target = message[5:].strip()
            # Basic validation for hostname / IP (alphanumeric, dots, dashes)
            if re.match(r'^[\w\.-]+$', target):
                intent = "NETWORK_TEST"
                action_payload = {"command": f"ping {target}"}
            else:
                return Decision(
                    situation_summary="Invalid ping target.",
                    observations=[f"Target contains invalid characters: {target}"],
                    inferences=["Target validation failed."],
                    risks=["Command injection"],
                    recommended_actions=[],
                    confidence=1.0,
                    requires_deep_analysis=False,
                    decision_rationale="That command cannot be executed because it is outside the ATLAS safety policy."
                )

        # 3. Decision Construction
        if intent:
            return Decision(
                situation_summary=f"User requested {intent}.",
                observations=[f"User message: {message}"],
                inferences=[f"Detected intent {intent}."],
                risks=[],
                recommended_actions=[{
                    "action_type": "OSCommandAction",
                    "payload": action_payload
                }],
                confidence=1.0,
                requires_deep_analysis=False,
                decision_rationale=f"Executing {intent} via OSCommandAction."
            )
        
        # 4. Fallback or Unsupported
        # Instead of falling back to FakeReasoner which gives dummy data, we should explicitly reject unsupported commands for the Assistant.
        # But wait, the requirements state: "For unsupported commands: status: unsupported, message: I understand the request, but that action is not currently enabled in ATLAS."
        return Decision(
            situation_summary="Unsupported user request.",
            observations=[f"User message: {message}"],
            inferences=["Intent not matched in CommandReasoner."],
            risks=[],
            recommended_actions=[],
            confidence=1.0,
            requires_deep_analysis=False,
            decision_rationale="I understand the request, but that action is not currently enabled in ATLAS."
        )
