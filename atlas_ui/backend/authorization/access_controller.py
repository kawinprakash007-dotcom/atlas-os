from atlas_ui.backend.authorization.permissions import get_permissions_for_role

class AccessController:
    def has_permission(self, role: str, permission: str) -> bool:
        if not role or not permission:
            return False
        role_permissions = get_permissions_for_role(role)
        return permission in role_permissions
