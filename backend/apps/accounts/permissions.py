from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsManagerOrReadOnly(BasePermission):
    """Any logged-in user can read; only admins/managers can create, edit or delete."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_manager_or_admin
