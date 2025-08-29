from django.shortcuts import render
from manager.manager import MT5AccountService
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.conf import settings

from utils.helper import *
from manager.interface import NewAccountData
from trading.models import MT5User


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
            # mt5_service = MT5AccountService(
            #     address=settings.METATRADER_SERVER,
            #     login=settings.METATRADER_LOGIN,
            #     password=settings.METATRADER_PASSWORD,
            #     user_group=settings.METATRADER_USERGROUP,
            # )
            # mt5_service.connect()

            # mt5_user, master_password = mt5_service.createUser({
            #     'first_name': data["first_name"],
            #     'last_name': data["last_name"],
            #     'balance': data["balance"],
            #     'country': data["country"],
            #     'company': settings.GLOBAL_SERVICE_NAME,
            #     'address': data["address"],
            #     'email': data["email"],
            #     'phone': data["phone"],
            #     'zip_code': data["zip_code"],
            #     'state': data["state"],
            #     'city': data["city"],
            #     'language': 'english',
            #     'comment': f"{settings.GLOBAL_SERVICE_NAME} Challenge Account ({data['challenge_name']})",
            # })
            mt5_user = MT5User.objects.get(login=4002)
            master_password='syusoas'
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