from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from account.models import CustomAuthToken
from django.db import close_old_connections
from asgiref.sync import sync_to_async

@sync_to_async
def get_user_from_token(token_key):
    try:
        # print('token key', token_key)
        token = CustomAuthToken.objects.get(access_token=token_key)
        # print('token instance', token)
        if token.has_access_expired():
            return None
        print('token instance', token)
        return token.user
    except CustomAuthToken.DoesNotExist:
        print('token error', token_key)
        return None

class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        close_old_connections()

        token_key = None
        # Extract token from query string instead of subprotocol
        query_string = scope.get('query_string', b'').decode()
        if 'token=' in query_string:
            # Parse token from query params
            for param in query_string.split('&'):
                if param.startswith('token='):
                    token_key = param.split('token=')[1]
                    break

        user = None
        if token_key:
            user = await get_user_from_token(token_key)

        if user is None:
            scope["user"] = AnonymousUser()
        else:
            scope["user"] = user

        return await super().__call__(dict(scope), receive, send)

def TokenAuthMiddlewareStack(inner):
    from channels.auth import AuthMiddlewareStack
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))
