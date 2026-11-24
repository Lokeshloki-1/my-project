from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsManagerOrReadOnly(BasePermission):
    """Any logged-in user can read; only admins/managers can create, edit or delete."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_manager_or_admin


class IsFinanceOrReadOnly(BasePermission):
    """Any logged-in user can read; admins, managers and accountants can record billing changes."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.is_manager_or_admin or request.user.role == "accountant"
