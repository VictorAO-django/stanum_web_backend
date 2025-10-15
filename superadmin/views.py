import json, io, base64, qrcode, pyotp
from decimal import Decimal
from django.utils.decorators import method_decorator
from django.http import Http404
from django.db.models import Sum, Avg, Count, Max, Min
from django.views.decorators.cache import cache_page
from django.utils.dateparse import parse_datetime
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
from utils.bridge_api import BridgeApi

from challenge.models import *
from trading.serializers import MT5UserSerializer
from account.serializers import MessageSerializer, TicketSerializer

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

class TradingUserListView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = AdminMT5UserSerializer
    queryset = MT5User.objects.all().order_by('-created_at')
    pagination_class = StandardResultsSetPagination
    filterset_class = MT5UserFilter
    filter_backends = [DjangoFilterBackend]

    def get(self, request, *args, **kwargs):
        users = MT5User.objects.all()
        pending_withdrawal = PropFirmWalletTransaction.objects.filter(type='debit', status='pending')
        total_referrals = Referral.objects.exclude(referred_by=None)
        res = super().get(request, *args, **kwargs)
        return Response({
            "total_trading_users": users.count(),
            "pending_withdrawal": pending_withdrawal.count(),
            "total_referrals": total_referrals.count(),
            "result": res.data
        }, status=status.HTTP_200_OK)

class TradingAccountListView(generics.ListAPIView):
    permission_classes=[permissions.IsAdminUser]
    serializer_class = AdminMT5AccountSerializer
    queryset = MT5Account.objects.all().order_by("-created_at")
    pagination_class = LargeResultsSetPagination
    filterset_class = MT5AccountFilter
    filter_backends = [DjangoFilterBackend]

    def get(self, request, *args, **kwargs):
        accounts = MT5Account.objects.all()
        positions = MT5Position.objects.filter(closed=False)
        funded = accounts.filter(funded=True)
        total_equity = accounts.aggregate(total=Sum("equity"))['total'] or 0

        res = super().get(request, *args, **kwargs)
        return Response({
            "total_accounts": accounts.count(),
            "active_positions": positions.count(),
            "total_equity": total_equity,
            "funded_account": funded.count(),
            "result": res.data
        }, status=status.HTTP_200_OK)


class PositionsListView(generics.ListAPIView):
    # authentication_classes=[]
    # permission_classes=[permissions.AllowAny]
    permission_classes=[permissions.IsAdminUser]
    serializer_class=AdminMT5PositionSerializer

    def get_queryset(self):
        login = self.kwargs.get("login")
        querysets = MT5Position.objects.filter(login=login, closed=False)
        self.query_count = querysets.count()
        return querysets
    
    def get(self, request, login, *args, **kwargs):
        account = MT5Account.objects.get(login=login)

        res = super().get(request, *args, **kwargs)
        return Response({
            'balance':account.balance,
            'equity': account.equity,
            'total_positions': self.query_count,
            'result': res.data
        })

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

class ProofOfIDActionView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def post(self, request, id, *args, **kwargs):
        data = request.data.get('status', 'pending')
        if data in ['approved', 'rejected']:
            user =get_object_or_404(User, id=id)
            proof = get_object_or_404(ProofOfIdentity, user=user)
            proof.status = data
            proof.reviewed_at=timezone.now()
            proof.save()
            if data=='approved':
                Mailer(user.email).kyc(user, 'proof_of_id_approved')
            if data=='rejected':
                Mailer(user.email).kyc(user, 'proof_of_id_rejected')
            return Response({'status': 'Ok'}, status=status.HTTP_200_OK)
        return Response({'status': 'Bad Request'}, status=status.HTTP_400_BAD_REQUEST)


class ProofOfAddress1ActionView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def post(self, request, id, *args, **kwargs):
        data = request.data.get('status', 'pending')
        if data in ['approved', 'rejected']:
            user =get_object_or_404(User, id=id)
            proof = get_object_or_404(ProofOfAddress, user=user, address_type='home_address_1')
            proof.status = data
            proof.reviewed_at=timezone.now()
            proof.save()
            if data=='approved':
                Mailer(user.email).kyc(user, 'proof_of_ha1_approved')
            if data=='rejected':
                Mailer(user.email).kyc(user, 'proof_of_ha1_rejected')
            return Response({'status': 'Ok'}, status=status.HTTP_200_OK)
        return Response({'status': 'Bad Request'}, status=status.HTTP_400_BAD_REQUEST)


class ProofOfAddress2ActionView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def post(self, request, id, *args, **kwargs):
        data = request.data.get('status', 'pending')
        if data in ['approved', 'rejected']:
            user =get_object_or_404(User, id=id)
            proof = get_object_or_404(ProofOfAddress, user=user, address_type='home_address_2')
            proof.status = data
            proof.reviewed_at=timezone.now()
            proof.save()
            if data=='approved':
                Mailer(user.email).kyc(user, 'proof_of_ha2_approved')
            if data=='rejected':
                Mailer(user.email).kyc(user, 'proof_of_ha2_rejected')
            return Response({'status': 'Ok'}, status=status.HTTP_200_OK)
        return Response({'status': 'Bad Request'}, status=status.HTTP_400_BAD_REQUEST)

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

class TicketListCreateAPIView(generics.ListAPIView):
    serializer_class = TicketSerializer
    permission_classes=[permissions.IsAdminUser]

    def get_queryset(self):
        return Ticket.objects.all().order_by("-created_at")
    

class MessageListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes=[permissions.IsAdminUser]

    def perform_create(self, serializer):
        ticket_id = self.kwargs["ticket_id"]
        ticket = get_object_or_404(Ticket, ticket_id=ticket_id, status='open')
        serializer.save(ticket=ticket, sender=self.request.user)
        

    def get_queryset(self):
        ticket_id = self.kwargs.get("ticket_id", None)
        ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
        return ticket.messages.order_by("created_at")


class CloseTicketApiView(APIView):
    permission_classes=[permissions.IsAdminUser]
    
    def post(self, request, ticket_id, *args, **kwargs):
        ticket = get_object_or_404(Ticket, ticket_id=ticket_id)
        ticket.status = 'closed'
        ticket.save()
        return Response({'status': 'Ok'}, status=status.HTTP_200_OK)
    

class IssueFundedAccountAPIView(APIView):
    permission_classes=[permissions.IsAdminUser]
    def post(self, request, login, *args, **kwargs):
        return custom_response(
                status="Forbidden",
                message="Funded Account Already issues for this completed challenge account",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        challenge_mt5_user = get_object_or_404(MT5User, login=login, account_type='challenge')
        if challenge_mt5_user.funded_account_issued:
            return custom_response(
                status="Forbidden",
                message="Funded Account Already issues for this completed challenge account",
                data={},
                http_status=status.HTTP_403_FORBIDDEN
            )
        
        user = challenge_mt5_user.user
        first_name, last_name = split_full_name(user.full_name)
        address = Address.objects.get(user=user)

        if challenge_mt5_user.challenge.challenge_class == 'challenge':
            challenge = PropFirmChallenge.objects.filter(challenge_class='challenge_funding').first()

        if challenge_mt5_user.challenge.challenge_class == 'skill_check':
            challenge = PropFirmChallenge.objects.filter(challenge_class='skill_check_funding').first()

        if not challenge:
            return custom_response(
                status="Bad Request",
                message="Corresponding funded account configuration cannot be found",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )
        
        balance = float(challenge.account_size)
        result = create_mt5_account(
            base_url=settings.BRIDGE_URL,
            account_data={
                'first_name': first_name,
                'last_name': last_name,
                'balance': balance,
                'country': user.country,
                'company': settings.GLOBAL_SERVICE_NAME,
                'address': address.home_address,
                'email': user.email,
                'phone': user.phone_number,
                'zip_code': address.zip_code,
                'state': address.state,
                'city': address.town,
                'language': 'english',
                'comment': f"{settings.GLOBAL_SERVICE_NAME} Challenge Account ({challenge.name})",
                'challenge_name': challenge.name,
            }
        )

        if result:
            mt5_user_login, password = result
            mt5_user = MT5User.objects.filter(login=mt5_user_login).first()
            if mt5_user:
                mt5_user.user = user
                mt5_user.challenge = challenge
                mt5_user.account_type = 'funded'
                mt5_user.password = encrypt_password(password)
                mt5_user.save()

                #Mark as issued
                challenge_mt5_user.funded_account_issued = True
                challenge_mt5_user.save()

                #Create Account Earning
                target_profit_amount = (challenge.profit_target_percent / Decimal(100)) * challenge.account_size
                AccountEarnings.objects.create(login=mt5_user.login, target=target_profit_amount)


                #Issue Certificate
                completed_challenge_profit_target =  (challenge_mt5_user.challenge.profit_target_percent / Decimal(100)) * challenge_mt5_user.challenge.account_size
                certificate=ChallengeCertificate.objects.create(
                    user=user, 
                    challenge_class = challenge_mt5_user.challenge.challenge_class,
                    name = challenge_mt5_user.challenge.name,
                    account_size = challenge_mt5_user.challenge.account_size,
                    profit=completed_challenge_profit_target
                )

                #Send email
                mailer = Mailer(user.email)
                mailer.funded_account_issued(mt5_user, challenge, password)
                mailer.certificate_issued(certificate)

                print("Account created:", mt5_user_login, password)
                return custom_response(
                    status="ok",
                    message="Funded account successfully created.",
                    data={},
                    http_status=status.HTTP_200_OK
                )
        else:
            print("Failed to create account")
            return custom_response(
                status="Bad Request",
                message="Error creating funded account.",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )


class AdminDashboardView(APIView):
    permission_classes=[permissions.IsAdminUser]

    def get(self, request, *args, **kwargs):
        users = User.objects.filter(is_deleted=False)
        competitions = Competition.objects.filter(ended=False)
        pending_withdrawal = PropFirmWalletTransaction.objects.filter(type='debit', status='pending')
        volume = 0
        recent_activity = ChallengeLog.objects.all().order_by("-id")[:10]

        competition_status = CompetitionStatusSerializer(competitions, many=True)
        recent_activity = ChallengeLogSerializer(recent_activity, many=True)
        return Response({
            "users": users.count(),
            "competitions": competitions.count(),
            "volume": volume,
            "pending_withdrawal": pending_withdrawal.count(),
            "competition_status": competition_status.data,
            "recent_activity": recent_activity.data
        }, status=status.HTTP_200_OK)
    


class CompetitionListAPIView(generics.ListAPIView):
    authentication_classes=[]
    permission_classes=[permissions.AllowAny]
    # permission_classes = [permissions.IsAdminUser]
    queryset=Competition.objects.all().order_by("-id")
    serializer_class=AdminCompetitionSerializer
    filterset_class = CompetitionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination

    def get(self, request, *args, **kwargs):
        res = super().get(request, *args, **kwargs)
        competitions = self.queryset
        active = competitions.filter(ended=False)
        contestants = MT5User.objects.filter(competition__isnull=False)
        total_prize_pool = competitions.aggregate(total=Sum("price_pool_cash"))["total"] or 0

        return Response({
            "active": active.count(),
            "participants": contestants.count(),
            "total_prize": total_prize_pool,
            "results": res.data
        })
    
    

class EndCompetitionView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request, uuid, *args, **kwargs):
        competition = get_object_or_404(Competition, uuid=uuid, ended=False)
        # bridge = BridgeApi() 
        # bridge.post(f'end-competiton/{competition.uuid}', {})

        return Response({"message": "processed"}, status=status.HTTP_200_OK)


class CompetitionCreateView(generics.CreateAPIView):
    authentication_classes=[]
    permission_classes=[permissions.AllowAny]
    # permission_classes = [permissions.IsAdminUser]
    serializer_class=CreateCompetitionSerializer
    queryset=Competition.objects.all()

