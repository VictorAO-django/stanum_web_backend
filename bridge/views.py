from django.shortcuts import render
import MT5Manager, traceback
from dataclasses import asdict
from sub_manager.manager import MT5AccountService
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings
from django.shortcuts import get_object_or_404

from utils.helper import *
from sub_manager.interface import NewAccountData
from trading.models import MT5User, AccountEarnings, MT5Account
from sub_manager.transformer import *
from sub_manager.producer import p

def broadcast_account(account:MT5Account):
    challenge = account.mt5_user.challenge
    competition = account.mt5_user.competition

    if challenge:
        ch_data = transform_propfirmchallenge(challenge)
        data = {
            'login': account.login,
            'account': {
                'created_at': account.created_at,
                'active': account.active,
                'step': account.step,
            },
            'challenge': asdict(ch_data),
        }
        p.produce(
            "account_challenge_initiate", 
            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
        )
    
    elif competition:
        cx_data = transform_competition(account.mt5_user.competition)
        data = {
            'login': account.login,
            'competition': asdict(cx_data),
        }
        p.produce(
            "account_competition_initiate", 
            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
        )
    p.flush()


def broadcast_account_with_challenge(account:MT5Account, challenge):
    if challenge:
        ch_data = transform_propfirmchallenge(challenge)
        data = {
            'login': account.login,
            'account': {
                'created_at': account.created_at,
                'active': account.active,
                'step': account.step,
            },
            'challenge': asdict(ch_data),
        }
        p.produce(
            "account_challenge_initiate", 
            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
        )
    p.flush()

def broadcast_account_with_competition(account:MT5Account, competition):
    if competition:
        cx_data = transform_competition(competition)
        data = {
            'login': account.login,
            'competition': asdict(cx_data),
        }
        p.produce(
            "account_competition_initiate", 
            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
        )
    p.flush()

class CreateAccountView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        secret = request.headers.get("X-BRIDGE-SECRET")
        data: NewAccountData = request.data
        mt5_service = None
        print("Data", data)

        # Validate secret
        if settings.BRIDGE_SECRET != secret:
            return custom_response(
                status="error",
                message="Invalid secret",
                data={},
                http_status=status.HTTP_403_FORBIDDEN,
            )

        try:
            mt5_service = MT5AccountService(
                address=settings.METATRADER_SERVER,
                login=settings.METATRADER_LOGIN,
                password=settings.METATRADER_PASSWORD,
                user_group=settings.METATRADER_USERGROUP,
            )
            mt5_service.connect()

            mt5_user, master_password = mt5_service.createUser({
                'first_name': data["first_name"],
                'last_name': data["last_name"],
                'balance': data["balance"],
                'country': data["country"],
                'company': settings.GLOBAL_SERVICE_NAME,
                'address': data["address"],
                'email': data["email"],
                'phone': data["phone"],
                'zip_code': data["zip_code"],
                'state': data["state"],
                'city': data["city"],
                'language': 'english',
                'comment': f"{settings.GLOBAL_SERVICE_NAME} Challenge Account ({data['challenge_name']})",
            })
            # mt5_user = MT5User.objects.get(login=4002)
            # master_password='X9p!wT2@jK7z'
            account, created = MT5Account.objects.get_or_create(mt5_user=mt5_user, login=mt5_user.login)

            challenge_id = data.get("challenge_id", None)
            if challenge_id:
                try:
                    challenge = PropFirmChallenge.objects.get(id=challenge_id)
                    broadcast_account_with_challenge(account, challenge)
                except Exception as err:
                    traceback.print_exc()
                    print("Error occured while broadcasting account to kafka", str(err))

            competition_id = data.get('competition_id', None)
            if competition_id:
                try:
                    competition = Competition.objects.get(id=competition_id)
                    broadcast_account_with_competition(account, competition)
                except Exception as err:
                    traceback.print_exc()
                    print("Error occured while broadcasting account to kafka", str(err))
                    
            print(f"({mt5_user.login})password", master_password)
            
            return custom_response(
                status='success',
                message="Account successfully created",
                data={
                    'mt5_user_login': mt5_user.login,
                    'password': master_password
                }
            )

        except Exception as e:
            print(f"MT5 account creation failed for user: {e}")
            print(f"MT5 error: {MT5Manager.LastError()}")
            return custom_response(
                status='error',
                message=f"MT5 account creation failed for user: {e}",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )
        finally:
            if mt5_service:
                mt5_service.disconnect()


class TestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        secret = request.headers.get("X-BRIDGE-SECRET")
        print("Test request received", secret)
        return Response({'status':'OK'}, status=status.HTTP_200_OK)
    


class DispatchAccountChallenge(APIView):
    authentication_classes=[]
    permission_classes=[AllowAny]
    def post(self, request, *args, **kwargs):
        secret = request.headers.get("X-BRIDGE-SECRET")
        if settings.BRIDGE_SECRET != secret:
            return custom_response(
                status="error",
                message="Invalid secret",
                data={},
                http_status=status.HTTP_403_FORBIDDEN,
            )
        
        for account in MT5Account.objects.filter(active=True, mt5_user__competition__isnull=True):
            broadcast_account(account)

        return Response({"status": "processed"}, status=status.HTTP_200_OK)

class DispatchAccountCompetition(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    def post(self, request, uuid, *args, **kwargs):
        secret = request.headers.get("X-BRIDGE-SECRET")
        if settings.BRIDGE_SECRET != secret:
            return custom_response(
                status="error",
                message="Invalid secret",
                data={},
                http_status=status.HTTP_403_FORBIDDEN,
            )
        
        ctx = get_object_or_404(Competition, uuid=uuid, ended=False)
        accounts = MT5Account.objects.filter(competition=ctx)
        for account in accounts:
            broadcast_account_with_competition(account, ctx)
        
        return Response({"status": "processed"}, status=status.HTTP_200_OK)

class EndCompetitionView(APIView):
    authentication_classes=[]
    permission_classes=[AllowAny]

    def post(self, request, uuid, *args, **kwargs):
        secret = request.headers.get("X-BRIDGE-SECRET")
        if settings.BRIDGE_SECRET != secret:
            return custom_response(
                status="error",
                message="Invalid secret",
                data={},
                http_status=status.HTTP_403_FORBIDDEN,
            )
        
        competition = get_object_or_404(Competition, uuid=uuid)
        data = {
            "action": "finalize_competition",
            "competition_uuid": competition.uuid,
            "triggered_by": "admin",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        p.produce(
            "competition.control", 
            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
        )
        p.flush()

        return Response({"status": "Processed"}, status=status.HTTP_200_OK)