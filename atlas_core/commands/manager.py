from typing import Optional, Dict, Any
from atlas_core.commands.models import DeviceCommand
from atlas_core.commands.registry import CommandRegistry
from atlas_core.commands.dispatcher import DeviceCommandDispatcher
from atlas_core.devices.registry import DeviceRegistry
from atlas_core.devices.health import DeviceHealthManager

class DeviceCommandManager:
    def __init__(
        self,
        device_registry: DeviceRegistry,
        command_registry: CommandRegistry,
        command_dispatcher: DeviceCommandDispatcher,
        health_manager: Optional[DeviceHealthManager] = None
    ):
        self.device_registry = device_registry
        self.command_registry = command_registry
        self.command_dispatcher = command_dispatcher
        self.health_manager = health_manager

    def send_command(
        self,
        target_device: str,
        command_type: str,
        payload: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> DeviceCommand:
        # Create trace block in registry as PENDING
        t_device = target_device if isinstance(target_device, str) else "UNKNOWN"
        c_type = command_type if isinstance(command_type, str) else "UNKNOWN"

        cmd = self.command_registry.create_command(
            target_device=t_device,
            command_type=c_type,
            payload=payload,
            metadata=metadata
        )
        command_id = cmd.command_id

        # 1. Structural Validation
        rejection_reason = None
        if not isinstance(target_device, str) or not target_device.strip():
            rejection_reason = "target_device must be a non-empty string."
        elif not isinstance(command_type, str) or not command_type.strip():
            rejection_reason = "command_type must be a non-empty string."
        elif payload is not None and not isinstance(payload, dict):
            rejection_reason = "payload must be a dictionary."

        if rejection_reason:
            self.command_registry.update_status(command_id, "REJECTED", error=rejection_reason)
            return self.command_registry.get_command(command_id)

        # 2. Registry checks
        if not self.device_registry.device_exists(target_device):
            self.command_registry.update_status(
                command_id, "REJECTED", error=f"Target device '{target_device}' is not registered."
            )
            return self.command_registry.get_command(command_id)

        # 3. Health check (Strict ONLINE enforcement)
        if self.health_manager is not None:
            try:
                status = self.health_manager.evaluate_device(target_device)
            except Exception:
                status = "OFFLINE"
        else:
            dev = self.device_registry.get_device(target_device)
            status = dev.status if dev else "OFFLINE"

        if status != "ONLINE":
            self.command_registry.update_status(
                command_id, "REJECTED", error=f"Target device '{target_device}' is {status}, not ONLINE."
            )
            return self.command_registry.get_command(command_id)

        # Retrieve device deep-copy for transport dispatching
        device = self.device_registry.get_device(target_device)

        # 4. Dispatch to transport
        # Transition PENDING -> DISPATCHED
        cmd = self.command_registry.update_status(command_id, "DISPATCHED")

        try:
            res = self.command_dispatcher.dispatch(cmd, device)

            acknowledged = res.get("acknowledged", True)
            success = res.get("success", False)
            result_data = res.get("result")
            err_msg = res.get("error")

            if acknowledged:
                self.command_registry.update_status(command_id, "ACKNOWLEDGED")

            # Transition to EXECUTING
            self.command_registry.update_status(command_id, "EXECUTING")

            if success:
                self.command_registry.update_status(command_id, "COMPLETED", result=result_data)
            else:
                self.command_registry.update_status(command_id, "FAILED", error=err_msg or "Device command execution failed.")

        except Exception as e:
            # Handle handler/transport exceptions safely
            self.command_registry.update_status(command_id, "FAILED", error=str(e))

        return self.command_registry.get_command(command_id)
