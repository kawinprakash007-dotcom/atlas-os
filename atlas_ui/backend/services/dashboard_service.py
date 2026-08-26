from typing import Dict, Any, Optional

class DashboardService:
    def get_dashboard_data(self, role: str) -> Dict[str, Any]:
        """
        Returns mock dashboard statistics tailored specifically for the user's role.
        """
        role_upper = role.upper()
        
        # Shared User-level view parameters
        devices = [
            {"device_id": "esp32_01", "device_type": "esp32", "status": "ONLINE", "last_seen": "Just now"},
            {"device_id": "rpi_01", "device_type": "raspberrypi", "status": "ONLINE", "last_seen": "1 min ago"},
            {"device_id": "drone_01", "device_type": "drone", "status": "ONLINE", "last_seen": "3 min ago"}
        ]
        recent_events = [
            {"event_id": "ev_01", "event_type": "person_entered", "source": "atlas_vision_01", "timestamp": "10s ago"},
            {"event_id": "ev_02", "event_type": "object_moved", "source": "rpi_01", "timestamp": "1m ago"}
        ]
        alerts = [
            {"alert_id": "al_01", "severity": "WARNING", "message": "High processor usage on drone_01", "timestamp": "3m ago"}
        ]

        data = {
            "role": role_upper,
            "system_status": "ONLINE",
            "devices": devices,
            "recent_events": recent_events,
            "alerts": alerts,
            "admin_controls": None
        }

        # Elevated ADMIN controls payload
        if role_upper == "ADMIN":
            data["admin_controls"] = {
                "active_users": 2,
                "security_logs_active": True,
                "registrations_allowed": True,
                "system_configuration": {
                    "mode": "autonomous",
                    "reasoning_threshold": 0.85,
                    "debug_logs": False
                }
            }

        return data
