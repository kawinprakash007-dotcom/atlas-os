import os
import psutil
import platform
import socket
import time
from typing import Dict, Any

class SystemMonitor:
    """
    Read-only OS telemetry collector.
    Avoids all subprocess usage, relying on cross-platform standard libraries
    and psutil.
    """
    
    def __init__(self):
        self.boot_time = psutil.boot_time()

    def _get_local_ip(self) -> str:
        try:
            # A safe way to get the local IP address connecting to the internet
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            # Fallback
            return socket.gethostbyname(socket.gethostname())

    def get_telemetry(self) -> Dict[str, Any]:
        """
        Gathers safe, read-only system telemetry.
        """
        # CPU
        cpu_usage = psutil.cpu_percent(interval=None) # Non-blocking immediate reading
        cpu_cores = psutil.cpu_count(logical=True)

        # RAM
        mem = psutil.virtual_memory()
        
        # Disk (root)
        try:
            # Use standard C: on Windows, / on Linux/Mac
            path = "C:\\" if platform.system() == "Windows" else "/"
            disk = psutil.disk_usage(path)
            disk_percent = disk.percent
            disk_free_gb = disk.free / (1024 ** 3)
        except Exception:
            disk_percent = 0.0
            disk_free_gb = 0.0

        # OS
        os_info = f"{platform.system()} {platform.release()}"
        hostname = socket.gethostname()
        
        # Uptime
        uptime_seconds = time.time() - self.boot_time
        
        # Network
        local_ip = self._get_local_ip()
        
        # Check basic connectivity via stats
        net_stats = psutil.net_if_stats()
        network_status = "Connected" if any(getattr(stat, 'isup', False) for stat in net_stats.values()) else "Disconnected"

        return {
            "cpu": {
                "usage_percent": cpu_usage,
                "cores": cpu_cores
            },
            "memory": {
                "usage_percent": mem.percent,
                "available_gb": mem.available / (1024 ** 3)
            },
            "disk": {
                "usage_percent": disk_percent,
                "free_gb": disk_free_gb
            },
            "os": {
                "info": os_info,
                "hostname": hostname,
                "uptime_seconds": uptime_seconds
            },
            "network": {
                "status": network_status,
                "local_ip": local_ip
            }
        }
