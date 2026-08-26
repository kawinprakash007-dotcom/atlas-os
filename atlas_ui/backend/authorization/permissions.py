from typing import Set, List
from atlas_ui.backend.authorization import roles

# Permission definitions
VIEW_SYSTEM = "VIEW_SYSTEM"
VIEW_DEVICES = "VIEW_DEVICES"
VIEW_EVENTS = "VIEW_EVENTS"
VIEW_ALERTS = "VIEW_ALERTS"

MANAGE_DEVICES = "MANAGE_DEVICES"
MANAGE_USERS = "MANAGE_USERS"
MANAGE_ADMINS = "MANAGE_ADMINS"
REGISTER_FACE = "REGISTER_FACE"
SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
VIEW_SECURITY_LOGS = "VIEW_SECURITY_LOGS"

ROLE_PERMISSIONS = {
    roles.USER: {
        VIEW_SYSTEM,
        VIEW_DEVICES,
        VIEW_EVENTS,
        VIEW_ALERTS
    },
    roles.ADMIN: {
        VIEW_SYSTEM,
        VIEW_DEVICES,
        VIEW_EVENTS,
        VIEW_ALERTS,
        MANAGE_DEVICES,
        MANAGE_USERS,
        MANAGE_ADMINS,
        REGISTER_FACE,
        SYSTEM_CONFIGURATION,
        VIEW_SECURITY_LOGS
    }
}

def get_permissions_for_role(role: str) -> List[str]:
    perms = ROLE_PERMISSIONS.get(role.upper(), set())
    return sorted(list(perms))
