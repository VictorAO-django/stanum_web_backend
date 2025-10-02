from django.urls import re_path, path
from .consumers import *

websocket_urlpatterns = [
    re_path(r"ws/account/(?P<login>\w+)/?$", AccountStatsConsumer.as_asgi()),
    path('ws/test/', TestConsumer.as_asgi()),
    re_path(r'ws/account2/(?P<login>\d+)/?$', AccountConsumer.as_asgi()),
    re_path(r'ws/competition/(?P<competition_uuid>[^/]+)/?$', CompetitionConsumer.as_asgi()),
]