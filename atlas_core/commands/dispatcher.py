from typing import Dict, Any, Callable
from atlas_core.commands.models import DeviceCommand
from atlas_core.devices.models import Device

class DeviceCommandDispatcher:
    def __init__(self):
        self._transports: Dict[str, Callable[[DeviceCommand, Device], Any]] = {}

    def register_transport(self, device_type: str, handler: Callable[[DeviceCommand, Device], Any]):
        self._transports[device_type.lower()] = handler

    def dispatch(self, command: DeviceCommand, device: Device) -> Dict[str, Any]:
        dtype = device.device_type.lower()
        if dtype not in self._transports:
            raise KeyError(f"No transport handler registered for device type '{device.device_type}'.")

        handler = self._transports[dtype]
        
        # Execute handler
        res = handler(command, device)

        # Normalize handler result contract
        if not isinstance(res, dict):
            # Fallback wrapper for simple handlers
            res = {"success": bool(res), "acknowledged": True, "result": {}}

        normalized = {
            "acknowledged": bool(res.get("acknowledged", True)),
            "success": bool(res.get("success", False)),
            "result": res.get("result") if res.get("result") is not None else {},
            "error": res.get("error")
        }

        # Keep error clean and descriptive if success is False
        if not normalized["success"] and not normalized["error"]:
            normalized["error"] = "Device rejected command or returned unknown error."

        return normalized
