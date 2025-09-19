from django.urls import re_path, path
from .consumers import *

websocket_urlpatterns = [
    re_path(r"ws/account/(?P<login>\w+)/?$", AccountStatsConsumer.as_asgi())
]