from rest_framework.permissions import BasePermission

class Is2FAEnabled(BasePermission):
    """
    Allows access only to users with 2FA enabled.
    """

    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            getattr(request.user, "is_2fa_enabled", False)
        )
