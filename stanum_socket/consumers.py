from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer, AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import json
from asgiref.sync import sync_to_async
from utils.helper import *
from .helper import *
import logging
from account.models import *
from account.serializers import *
from trading.models import *

logger = logging.getLogger(__name__)


class AccountStatsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            self.login = self.scope['url_route']['kwargs']['login']
            self.group_name = f"account_{self.login}"

            # Check access before accepting
            if not await self.has_account_access():
                await self.close()
                return

            # Join the group for this account
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            print(f"Connected to {self.group_name}")
        except Exception as err:
            print("Error in connect:", err)
            await self.close()

    async def disconnect(self, close_code):
        print(f"DISCONNECT login={getattr(self, 'login', None)} code={close_code}")
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception as e:
            print("Error discarding group:", e)

    async def account_update(self, event):
        """Handle messages broadcast via group_send"""
        await self.send_json({
            "type": "account_stats",
            "data": event["data"]
        })

    @database_sync_to_async
    def has_account_access(self):
        """Verify that the connected user has access to this account"""
        try:
            user = self.scope["user"]
            print("USER", user)
            if not user or isinstance(user, AnonymousUser):
                return False
            MT5User.objects.get(login=self.login, user=user, account_status="active")
            print("MT5 USER EXIST")
            return True
        except MT5User.DoesNotExist:
            print("MT5 USER DONT EXIST")
            return False


class TestConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print(f"Headers: {dict(self.scope['headers'])}")
        print(f"Subprotocols: {self.scope.get('subprotocols', [])}")
        print(f"Origin: {dict(self.scope['headers']).get(b'origin', b'None')}")

        await self.accept()
        await self.send(text_data="IT WORKS!")