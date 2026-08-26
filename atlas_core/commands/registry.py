import uuid
import time
import copy
from typing import Dict, List, Optional, Any
from atlas_core.commands.models import DeviceCommand
from atlas_core.monitoring.metrics import SystemMetrics

class CommandRegistry:
    # State transitions check mapping
    ALLOWED_TRANSITIONS = {
        "PENDING": {"DISPATCHED", "REJECTED", "FAILED", "TIMEOUT"},
        "DISPATCHED": {"ACKNOWLEDGED", "EXECUTING", "COMPLETED", "FAILED", "TIMEOUT"},
        "ACKNOWLEDGED": {"EXECUTING", "COMPLETED", "FAILED", "TIMEOUT"},
        "EXECUTING": {"COMPLETED", "FAILED", "TIMEOUT"},
        "COMPLETED": set(),
        "FAILED": set(),
        "REJECTED": set(),
        "TIMEOUT": set()
    }

    def __init__(self, max_history: int = 1000, metrics: Optional[SystemMetrics] = None):
        self.max_history = max_history
        self.metrics = metrics or SystemMetrics()
        self._commands: List[DeviceCommand] = []
        self._command_map: Dict[str, DeviceCommand] = {}

    def create_command(
        self,
        target_device: str,
        command_type: str,
        payload: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> DeviceCommand:
        command_id = str(uuid.uuid4())
        cmd = DeviceCommand(
            command_id=command_id,
            target_device=target_device,
            command_type=command_type,
            payload=payload if payload is not None else {},
            created_at=time.time(),
            status="PENDING",
            metadata=metadata if metadata is not None else {}
        )

        self._commands.append(cmd)
        self._command_map[command_id] = cmd

        # Discard oldest history if max exceeded
        while len(self._commands) > self.max_history:
            removed = self._commands.pop(0)
            self._command_map.pop(removed.command_id, None)

        # Update metrics exactly once
        self.metrics.commands_total += 1

        return copy.deepcopy(cmd)

    def _get_internal(self, command_id: str) -> DeviceCommand:
        if command_id not in self._command_map:
            raise KeyError(f"Command ID '{command_id}' not found.")
        return self._command_map[command_id]

    def get_command(self, command_id: str) -> Optional[DeviceCommand]:
        cmd = self._command_map.get(command_id)
        if cmd is None:
            return None
        return copy.deepcopy(cmd)

    def list_recent(self, limit: int = 50) -> List[DeviceCommand]:
        limit = max(1, min(limit, self.max_history))
        recent = self._commands[-limit:]
        return [copy.deepcopy(c) for c in recent]

    def update_status(
        self,
        command_id: str,
        status: str,
        result: Optional[dict] = None,
        error: Optional[str] = None
    ) -> DeviceCommand:
        cmd = self._get_internal(command_id)
        current = cmd.status

        # Transition validation
        if current in ("COMPLETED", "FAILED", "REJECTED", "TIMEOUT"):
            raise ValueError(f"Cannot transition command '{command_id}' from terminal state '{current}'.")

        if status not in self.ALLOWED_TRANSITIONS[current]:
            raise ValueError(f"Invalid transition from state '{current}' to '{status}'.")

        # Set transition state and timestamps
        cmd.status = status
        now = time.time()

        if status == "DISPATCHED":
            cmd.dispatched_at = now
        elif status == "ACKNOWLEDGED":
            cmd.acknowledged_at = now
        elif status in ("COMPLETED", "FAILED", "REJECTED", "TIMEOUT"):
            cmd.completed_at = now
            if status == "COMPLETED":
                cmd.result = copy.deepcopy(result) if result is not None else {}
                self.metrics.commands_completed += 1
            elif status == "REJECTED":
                cmd.error = error
                self.metrics.commands_rejected += 1
            else: # FAILED or TIMEOUT
                cmd.error = error
                self.metrics.commands_failed += 1

        return copy.deepcopy(cmd)
