from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer, AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
import json, redis, traceback
from asgiref.sync import sync_to_async
from utils.helper import *
from .helper import *
import logging
from account.models import *
from account.serializers import *
from trading.models import *

REDIS_URL = settings.REDIS_URL
redis_pool = redis.ConnectionPool.from_url(
    REDIS_URL,
    decode_responses=True,
    max_connections=50
)
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



class AccountConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for individual account updates
    URL: ws://domain/ws/account/{login}/
    """
    
    async def connect(self):
        self.login = self.scope['url_route']['kwargs']['login']
        self.group_name = f'account_{self.login}'
        
        # Join account group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial account data
        await self.send_initial_account_data()
        
        logger.info(f"Account {self.login} WebSocket connected")
    
    async def disconnect(self, close_code):
        # Leave account group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        
        logger.info(f"Account {self.login} WebSocket disconnected")
    
    async def send_initial_account_data(self):
        """Send current account state when client connects"""
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            user_data = await redis_client.hgetall(f"user:{self.login}")
            await redis_client.close()
            
            if user_data:
                await self.send(text_data=json.dumps({
                    "type": "account_initial",
                    "data": {
                        "login": int(self.login),
                        "username": user_data.get("username", ""),
                        "current_equity": float(user_data.get("current_equity", 0)),
                        "return_percent": float(user_data.get("return_percent", 0)),
                        "max_drawdown": float(user_data.get("max_drawdown", 0)),
                        "total_trades": int(user_data.get("total_trades", 0)),
                        "win_rate": float(user_data.get("win_rate", 0)),
                    }
                }))
        except Exception as e:
            logger.error(f"Error sending initial account data: {e}")
    
    async def account_update(self, event):
        """
        Receive account updates from group_send
        Called when monitor broadcasts account updates
        """
        await self.send(text_data=json.dumps({
            "type": "account_update",
            "data": event["data"]
        }))


class CompetitionConsumer(AsyncWebsocketConsumer):
    """
    WebSocket for competition leaderboard updates
    URL: ws://domain/ws/competition/{competition_uuid}/
    """
    
    async def connect(self):
        self.competition_uuid = self.scope['url_route']['kwargs']['competition_uuid']
        self.group_name = f'competition_{self.competition_uuid}'
        
        # Join competition group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Send initial leaderboard
        await self.send_initial_leaderboard()
        
        logger.info(f"Competition {self.competition_uuid} WebSocket connected")
    
    async def disconnect(self, close_code):
        # Leave competition group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
        
        logger.info(f"Competition {self.competition_uuid} WebSocket disconnected")
    
    async def send_initial_leaderboard(self):
        """Send current leaderboard when client connects"""
        try:
            redis_client = redis.from_url(REDIS_URL, decode_responses=True)
            
            # Check competition status
            comp_meta = redis_client.hgetall(f"competition:{self.competition_uuid}:meta")
            
            # Get top 100 participants
            top_logins = redis_client.zrevrange(
                f"competition:{self.competition_uuid}:leaderboard",
                0, 99,
                withscores=True
            )
            
            leaderboard = []
            for rank, (login, score) in enumerate(top_logins, 1):
                user_data = redis_client.hgetall(f"user:{login}")
                
                if user_data:
                    leaderboard.append({
                        "rank": rank,
                        "login": int(login),
                        "username": user_data.get("username", ""),
                        "current_equity": float(user_data.get("current_equity", 0)),
                        "return_percent": float(user_data.get("return_percent", 0)),
                        "max_drawdown": float(user_data.get("max_drawdown", 0)),
                        "total_trades": int(user_data.get("total_trades", 0)),
                        "win_rate": float(user_data.get("win_rate", 0)),
                        "score": float(score)
                    })
            
            redis_client.close()
            
            await self.send(text_data=json.dumps({
                "type": "leaderboard_initial",
                "data": {
                    "competition": {
                        "uuid": self.competition_uuid,
                        "name": comp_meta.get("name", ""),
                        "status": comp_meta.get("status", ""),
                        "end_date": comp_meta.get("end_date", "")
                    },
                    "leaderboard": leaderboard
                }
            }))
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error sending initial leaderboard: {e}")
    
    async def leaderboard_update(self, event):
        """
        Receive leaderboard updates from group_send
        Called when monitor broadcasts leaderboard updates
        """
        await self.send(text_data=json.dumps({
            "type": "leaderboard_update",
            "data": event["data"]
        }))
    
    async def competition_ended(self, event):
        """
        Notify clients that competition has ended
        """
        await self.send(text_data=json.dumps({
            "type": "competition_ended",
            "data": event["data"]
        }))