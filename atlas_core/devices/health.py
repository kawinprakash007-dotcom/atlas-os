import time
from typing import Dict, Any, Optional
from atlas_core.devices.registry import DeviceRegistry

class DeviceHealthManager:
    def __init__(
        self,
        registry: DeviceRegistry,
        stale_threshold: float = 60.0,
        offline_threshold: float = 120.0
    ):
        self.registry = registry
        self.stale_threshold = stale_threshold
        self.offline_threshold = offline_threshold

    def evaluate_device(self, device_id: str, current_time: Optional[float] = None) -> str:
        """
        Evaluates the health of a specific device and updates its status in the registry.
        ONLINE if elapsed < stale_threshold.
        STALE if stale_threshold <= elapsed < offline_threshold.
        OFFLINE if elapsed >= offline_threshold.
        """
        device = self.registry.get_device(device_id)
        if device is None:
            raise KeyError(f"Device '{device_id}' does not exist.")

        t = current_time if current_time is not None else time.time()
        elapsed = t - device.last_seen

        if elapsed >= self.offline_threshold:
            status = "OFFLINE"
        elif elapsed >= self.stale_threshold:
            status = "STALE"
        else:
            status = "ONLINE"

        self.registry.update_device(device_id, status=status)
        return status

    def evaluate_all(self, current_time: Optional[float] = None) -> Dict[str, str]:
        """
        Evaluates and updates status for all registered devices.
        Returns a dict mapping device_id to its new status.
        """
        results = {}
        for device in self.registry.list_devices():
            status = self.evaluate_device(device.device_id, current_time=current_time)
            results[device.device_id] = status
        return results

    def get_system_summary(self, current_time: Optional[float] = None) -> Dict[str, Any]:
        """
        Performs a full health evaluation and returns a summary dict of counts.
        """
        self.evaluate_all(current_time=current_time)
        
        devices = self.registry.list_devices()
        total = len(devices)
        online = sum(1 for d in devices if d.status == "ONLINE")
        stale = sum(1 for d in devices if d.status == "STALE")
        offline = sum(1 for d in devices if d.status == "OFFLINE")

        return {
            "total": total,
            "online": online,
            "stale": stale,
            "offline": offline
        }
