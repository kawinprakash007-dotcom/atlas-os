import copy
import time
from typing import Dict, List, Optional, Any
from atlas_core.devices.models import Device

class DeviceRegistry:
    def __init__(self):
        # Internal storage mapping device_id -> Device
        self._devices: Dict[str, Device] = {}

    def register_device(
        self,
        device_id: str,
        device_type: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Device:
        """
        Registers a device. If the device already exists:
        - Raises ValueError if the device_type is different.
        - Otherwise updates capabilities and metadata, resets status to ONLINE,
          updates last_seen, and returns the updated device.
        """
        if not device_id:
            raise ValueError("device_id must be a non-empty string.")
        if not device_type:
            raise ValueError("device_type must be a non-empty string.")

        caps = list(capabilities) if capabilities is not None else []
        meta = dict(metadata) if metadata is not None else {}

        if device_id in self._devices:
            existing = self._devices[device_id]
            if existing.device_type != device_type:
                raise ValueError(
                    f"Device '{device_id}' already registered with type '{existing.device_type}', "
                    f"cannot re-register with type '{device_type}'."
                )
            # Update mutable fields safely
            existing.capabilities = caps
            existing.metadata = meta
            existing.status = "ONLINE"
            existing.last_seen = time.time()
            return copy.deepcopy(existing)

        # Create new device
        device = Device(
            device_id=device_id,
            device_type=device_type,
            capabilities=caps,
            status="ONLINE",
            metadata=meta,
            registered_at=time.time(),
            last_seen=time.time()
        )
        self._devices[device_id] = device
        return copy.deepcopy(device)

    def get_device(self, device_id: str) -> Optional[Device]:
        """
        Returns a deep copy of the Device if registered, else None.
        """
        device = self._devices.get(device_id)
        if device is None:
            return None
        return copy.deepcopy(device)

    def list_devices(self) -> List[Device]:
        """
        Returns a list of deep copies of all registered devices.
        """
        return [copy.deepcopy(d) for d in self._devices.values()]

    def update_device(self, device_id: str, **kwargs) -> Device:
        """
        Updates specific mutable fields of a registered device and returns a deep copy of the updated device.
        Allowed fields to update: capabilities, status, metadata, last_seen.
        Raises KeyError if device does not exist.
        """
        if device_id not in self._devices:
            raise KeyError(f"Device '{device_id}' does not exist.")

        device = self._devices[device_id]
        
        # Validate and apply updates
        for key, val in kwargs.items():
            if key == "capabilities":
                device.capabilities = list(val) if val is not None else []
            elif key == "metadata":
                device.metadata = dict(val) if val is not None else {}
            elif key == "status":
                if val not in ("ONLINE", "STALE", "OFFLINE"):
                    raise ValueError(f"Invalid status: {val}")
                device.status = val
            elif key == "last_seen":
                device.last_seen = float(val)
            elif key in ("device_id", "device_type", "registered_at"):
                raise ValueError(f"Field '{key}' is immutable and cannot be updated.")
            else:
                raise ValueError(f"Unknown field '{key}' cannot be updated.")

        return copy.deepcopy(device)

    def record_heartbeat(self, device_id: str) -> Device:
        """
        Records a heartbeat for the device: updates last_seen to current time and status to ONLINE.
        Raises KeyError if device does not exist.
        """
        if device_id not in self._devices:
            raise KeyError(f"Device '{device_id}' does not exist.")
        return self.update_device(device_id, last_seen=time.time(), status="ONLINE")

    def device_exists(self, device_id: str) -> bool:
        """
        Returns True if the device is registered, False otherwise.
        """
        return device_id in self._devices
