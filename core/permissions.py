from rest_framework.permissions import BasePermission, IsAuthenticated


class IsAppAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_admin
        )
