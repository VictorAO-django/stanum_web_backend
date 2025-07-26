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
        # print('token error', token_key)
        return None

class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        close_old_connections()

        token_key = None
        headers = dict(scope.get("headers", []))
        # Extract token from sec-websocket-protocol header
        protocol_header = headers.get(b'sec-websocket-protocol')
        if protocol_header:
            token_key = protocol_header.decode()

        user = None
        if token_key:
            user = await get_user_from_token(token_key)

        if user is None:
            scope["user"] = AnonymousUser()
        else:
            scope["user"] = user

        # IMPORTANT: Accept the connection with the protocols to avoid client disconnect!
        # Override send to add subprotocols to handshake response:
        async def send_wrapper(message):
            if message.get("type") == "websocket.accept":
                message.setdefault("subprotocol", token_key)
            await send(message)

        return await super().__call__(dict(scope), receive, send_wrapper)

def TokenAuthMiddlewareStack(inner):
    from channels.auth import AuthMiddlewareStack
    return TokenAuthMiddleware(AuthMiddlewareStack(inner))
