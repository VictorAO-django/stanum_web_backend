import json, io, base64, qrcode, pyotp
from decimal import Decimal
from django.utils.decorators import method_decorator
from django.http import Http404
from django.db.models import Sum, Avg, Count, Max, Min
from django.views.decorators.cache import cache_page
from django.utils.dateparse import parse_datetime
from metaapi_cloud_sdk import MetaApi
from django_filters.rest_framework import DjangoFilterBackend
from django.urls import reverse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.decorators import method_decorator
from datetime import datetime, timedelta
from django.utils.timezone import make_aware
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from rest_framework import status
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from django.contrib.auth import user_logged_in, user_logged_out, user_login_failed
from rest_framework import permissions
from django.db import transaction
from asgiref.sync import async_to_sync
from django.contrib.auth.tokens import default_token_generator

from .models import *
from .serializers import *
from utils.helper import *
from utils.otp import *
from utils.filters import *
from utils.pagination import *
from service.now_payment import NOWPaymentsService

from challenge.models import *

User = get_user_model()

class LoginView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    @swagger_auto_schema(
        operation_summary="Login Endpoint",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'email': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_EMAIL),
                'password': openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_PASSWORD),
            },
            required=['email', 'password'],
        ),
    )
    def post(self, request):
        password = request.data["password"]
        try:
            user = User.objects.get(email=request.data['email'].lower(), email_verified=True, is_deleted=False)
            if user.is_locked():
                return custom_response(
                    status="Error",
                    message="Too many attempts, try again in 5 minutes.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            if not user.is_superuser: 
                return custom_response(
                    status="Error",
                    message=f"Admin only.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
            trial_count, trial_valid = update_lock_count(user, 'increase')            
            if user.check_password(password):
                if user.email_verified:
                    token, created = CustomAuthToken.objects.get_or_create(
                        user_type=ContentType.objects.get_for_model(user),
                        user_id=user.id,
                    )
                    if not created:
                        token.refresh()
                    
                    trial_count, trial_valid = update_lock_count(user, 'fallback')

                    user_logged_in.send(sender=user.__class__, request=request, user=user)

                    return custom_response(
                        status="Success",
                        message="Login successful, Admin Authenticated!",
                        data={
                            'access': token.access_token,
                            'refresh': token.refresh_token,
                            'user': {
                                'email': user.email,
                                'full_name': user.full_name,
                            },
                        }
                    )
    
                else:
                    return custom_response(
                        status="Error",
                        message=f"Please Verify your email!, you have {5-trial_count} attempt(s) left.",
                        data={},
                        http_status=status.HTTP_400_BAD_REQUEST
                    )
            else: 
                user_login_failed.send(sender=user.__class__, credentials={'email': user.email}, request=request)
                return custom_response(
                    status="Error",
                    message=f"Incorrect credentials, you have {5-trial_count} attempt(s) left.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )
            
        except User.DoesNotExist:
            return custom_response(
                status="Error",
                message="Incorrect credentials",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )
        


class UserListView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = UserSerializer
    queryset = User.objects.filter(is_deleted=False).order_by('-id')
    pagination_class = StandardResultsSetPagination

class UserDetailView(generics.RetrieveAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = UserDetailSerializer
    queryset = User.objects.all()
    lookup_field='id'

class ChallengeListView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = ChallengeSerializer
    queryset = PropFirmChallenge.objects.all()
    pagination_class = StandardResultsSetPagination
    filterset_class = PropFirmChallengeFilter
    filter_backends = [DjangoFilterBackend]
    
class ChallengeCreateView(generics.CreateAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class=ChallengeSerializer
    queryset=PropFirmChallenge.objects.all()
    def post(self, request, *args, **kwargs):
        print("hahah")
        return super().post(request, *args, **kwargs)

class ChallengeDetailView(generics.RetrieveUpdateAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class=ChallengeSerializer
    queryset=PropFirmChallenge.objects.all()
    lookup_field='id'

class UserKYCView(generics.RetrieveAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class=UserKYCDataSerializer
    queryset=User.objects.all()
    lookup_field='id'

class UserWalletView(generics.RetrieveAPIView):
    serializer_class = UserWalletSerializer
    permission_classes = [ permissions.IsAdminUser]

    def get_object(self):
        user_id = self.kwargs.get('id')
        user = get_object_or_404(User, id=user_id)
        obj, _ = PropFirmWallet.objects.get_or_create(user=user)
        return obj
    
class UserWalletTransactionView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = UserWalletTransactionSerializer
    filterset_class = PropFirmWalletTransactionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination

    def get_queryset(self):
        user_id = self.kwargs.get('id')
        user = get_object_or_404(User, id=user_id)
        wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
        queryset = PropFirmWalletTransaction.objects.filter(wallet=wallet).order_by('-id')
        return queryset
    
class DeleteUserView(APIView):
    permission_classes=[permissions.IsAdminUser]
    def delete(self, request, id, *args, **kwargs):
        user = get_object_or_404(User, id=id)
        user.is_deleted = True
        user.save()
        return Response(status=status.HTTP_200_OK)
    
class PayoutsView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class=UserWalletTransactionSerializer
    queryset=PropFirmWalletTransaction.objects.filter(type='debit').exclude(pay_address="").order_by('-id')
    filterset_class = PropFirmWalletTransactionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination


class ApprovePayoutView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def post(self, request, id, *args, **kwargs):
        service = NOWPaymentsService()
        try:
            with transaction.atomic():
                trx = PropFirmWalletTransaction.objects.select_for_update().get(id=id)

                assert trx.type == 'debit', "Only a debit transaction can be approved"
                assert trx.status == 'pending', "Payout already processed"
                withdrawals = [{
                    'address': trx.pay_address,
                    'currency': trx.pay_currency,
                    'amount': float(trx.price_amount),
                    'ipn_callback_url':  request.build_absolute_uri(f'/api/v1/admin/payouts/{trx.id}/ipn')
                }]
                # result = service.create_payout(
                #     withdrawals,
                #     '',
                #     f'Withdrawal ${trx.transaction_id} for user {trx.wallet.user.email} approved by {request.user.email}'
                # )
                # print(result)
                
                # Now mark it approved
                # trx.payment_id = 
                trx.status = 'approved'
                trx.save()

            return custom_response(
                status="success",
                message="Transaction Processed.",
                data={}
            )

        except PropFirmWalletTransaction.DoesNotExist:
            return custom_response(
                status="error",
                message="Transaction not found",
                data={},
                http_status=status.HTTP_404_NOT_FOUND
            )
        except Exception as err:
            return custom_response(
                status="error",
                message=str(err),
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        

class RejectPayoutView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def post(self, request, id, *args, **kwargs):
        try:
            with transaction.atomic():
                trx = PropFirmWalletTransaction.objects.select_for_update().get(id=id)

                assert trx.type == 'debit', "Only a debit transaction can be approved"
                assert trx.status == 'pending', "Payout already processed"

                # Now mark it approved
                trx.status = 'rejected'
                trx.save()

            return custom_response(
                status="success",
                message="Rejection Processed.",
                data={}
            )

        except PropFirmWalletTransaction.DoesNotExist:
            return custom_response(
                status="error",
                message="Transaction not found",
                data={},
                http_status=status.HTTP_404_NOT_FOUND
            )
        except Exception as err:
            return custom_response(
                status="error",
                message=str(err),
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
