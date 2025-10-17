from functools import wraps
from rest_framework.response import Response
from rest_framework import status
from utils.helper import confirm_account_owner, custom_response

def require_account_owner(view_func):
    """Ensure the requesting user owns the MT5 account."""
    @wraps(view_func)
    def wrapper(self, request, login, *args, **kwargs):
        is_owner, mt5_user = confirm_account_owner(login, request.user)
        if not is_owner:
            return custom_response(
                status="error",
                message="Not Found",
                data={},
                http_status=status.HTTP_404_NOT_FOUND
            )
        # attach mt5_user to request for later use
        request.mt5_user = mt5_user
        return view_func(self, request, login, *args, **kwargs)
    return wrapper
