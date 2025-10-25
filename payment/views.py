import json, uuid, random, pyotp, time
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import generics
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import *
from .serializers import *
from service.now_payment import NOWPaymentsService
from utils.mailer import Mailer
from utils.decorators import require_account_owner

from asgiref.sync import async_to_sync

from challenge.models import *
from trading.models import *
from account.models import (
    Address
)

from service.paystack import PaystackService
from utils.helper import *
from utils.permission import *
from utils.pagination import *
from utils.filters import *

User = get_user_model()

class AvailableCurrenciesAPIView(APIView):
    """Get list of available cryptocurrencies"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        service = NOWPaymentsService()
        currencies = service.get_available_currencies()
        
        if 'error' in currencies:
            return Response(
                {'error': currencies['error']}, 
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response(currencies)
    
class AvailableFullCurrenciesAPIView(APIView):
    """Get list of available full cryptocurrencies"""
    authentication_classes=[]
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        service = NOWPaymentsService()
        currencies = service.get_available_full_currencies()
        
        if 'error' in currencies:
            return Response(
                {'error': currencies['error']}, 
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        return Response(currencies['currencies'], status=status.HTTP_200_OK)

class EstimateAPIView(APIView):
    """Get crypto amount estimate for fiat amount"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = EstimateSerializer(data=request.data)
        if serializer.is_valid():
            service = NOWPaymentsService()
            estimate = service.get_estimate(
                amount=serializer.validated_data['amount'],
                currency_from=serializer.validated_data['currency_from'],
                currency_to=serializer.validated_data['currency_to']
            )
            
            if 'error' in estimate:
                return Response(
                    {'error': estimate['error']}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            return Response(estimate)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PaymentCreateAPIView(APIView):
    """Create a new payment"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        payload = request.data.copy()
        
        is_contest = payload.get('is_contest', False)
        constest_uuid = payload.get('contest_uuid', "")
        if is_contest:
            contest = get_object_or_404(Competition, uuid=constest_uuid, ended=False)
            if not contest.is_active():
                return custom_response(
                    status="error",
                    message = "Contest is yet to start",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN
                )
            
            existing_account = MT5User.objects.filter(user=request.user, competition=contest)
            if existing_account.exists():
                return custom_response(
                    status="error",
                    message = "You can't purchase a contest account twice",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN
                )
                
            if payload.get('description', '') == '':
                payload['description'] = f"Stanum payment for challenge {contest.name}"
            
            order_id = f"STMCTX-{contest.id}-{request.user.id}"
            ipn_url_text = '/api/v1/payment/crypto/ipn/contest/'
            
        else:
            challenge_id = payload.get('challenge_id', '0')
            challenge = get_object_or_404(PropFirmChallenge, id=challenge_id, status='active')
            if challenge.exists():
                challenge = challenge.first()
            if payload.get('description', '') == '':
                payload['description'] = f"Stanum payment for challenge {challenge.name}"
            
            order_id = f"STMCLG-{challenge.id}-{request.user.id}"
            ipn_url_text = '/api/v1/payment/crypto/ipn/'

        print(ipn_url_text, order_id)
        print(payload)
        serializer = PaymentCreateSerializer(data=payload)
        if serializer.is_valid(): 
            # Create payment record
            payment, _ = Payment.objects.get_or_create(
                user=request.user,
                order_id=order_id,
                defaults={
                    'order_description': serializer.validated_data['description'],
                    'price_amount': serializer.validated_data['amount'],
                    'price_currency': serializer.validated_data['price_currency'],
                    'pay_currency': serializer.validated_data['currency']
                }
            )
            
            # Create payment with NOWPayments
            service = NOWPaymentsService()
            ipn_url = request.build_absolute_uri(ipn_url_text)
            
            result = service.create_payment(
                price_amount=serializer.validated_data['amount'],
                price_currency=serializer.validated_data['price_currency'],
                pay_currency=serializer.validated_data['currency'],
                order_id=order_id,
                order_description=serializer.validated_data['description'],
                ipn_callback_url=ipn_url
            )
            
            if 'error' in result:
                payment.delete()  # Clean up failed payment
                return Response(
                    {'error': result['error']}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update payment record with NOWPayments response
            payment.payment_id = result['payment_id']
            payment.pay_amount = result.get('pay_amount')
            payment.pay_address = result.get('pay_address')
            payment.save()
            
            # Return created payment
            response_serializer = PaymentSerializer(payment)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return custom_response(
            status="error",
            message = str(next(iter(serializer.errors.values()))[0]),
            data=serializer.errors,
            http_status=status.HTTP_403_FORBIDDEN
        )

class PaymentListAPIView(generics.ListAPIView):
    """List user's payments"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')

class PaymentDetailAPIView(generics.RetrieveAPIView):
    """Get payment details and update status"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)
    
    def retrieve(self, request, *args, **kwargs):
        payment = self.get_object()
        
        # Update payment status from NOWPayments
        if payment.payment_id:
            service = NOWPaymentsService()
            status_result = service.get_payment_status(payment.payment_id)
            
            if 'error' not in status_result:
                payment.payment_status = status_result['payment_status']
                payment.save()
        
        serializer = self.get_serializer(payment)
        return Response(serializer.data)

class PaymentStatusUpdateAPIView(APIView):
    """Manually refresh payment status"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, user=request.user)
        
        if not payment.payment_id:
            return Response(
                {'error': 'Payment not yet created with NOWPayments'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        service = NOWPaymentsService()
        status_result = service.get_payment_status(payment.payment_id)
        
        if 'error' in status_result:
            return Response(
                {'error': status_result['error']}, 
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # Update payment status
        old_status = payment.payment_status
        payment.payment_status = status_result['payment_status']
        payment.save()
        
        serializer = PaymentSerializer(payment)
        return Response({
            'payment': serializer.data,
            'status_changed': old_status != payment.payment_status
        })

@method_decorator(csrf_exempt, name='dispatch')
class PaymentIPNAPIView(APIView):
    """Handle IPN callbacks from NOWPayments"""
    permission_classes = []  # No authentication required for IPN
    
    def post(self, request):
        try:
            # Verify signature
            # signature = request.headers.get('x-nowpayments-sig')
            # if not signature:
            #     return Response({'error': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            service = NOWPaymentsService()
            # if not service.verify_ipn_signature(request.body, signature):
            #     return Response({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
            print("Payment IPN received")
            # Parse callback data
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update payment status
            try:
                _, challenge_id, user_id = data['order_id'].split('-')
                challenge = get_object_or_404(PropFirmChallenge, id=challenge_id)
                user = get_object_or_404(User, id=user_id)

                payment = Payment.objects.get(order_id=data['order_id'])
                old_status = payment.payment_status

                print("Payment Status", data['payment_status'])
                if old_status != data['payment_status']:
                    payment.payment_status = data['payment_status']
                    if 'pay_amount' in data:
                        payment.pay_amount = data['pay_amount']
                    payment.save()
                    
                    # Handle different payment statuses
                    if data['payment_status'] == 'finished':
                        # Payment completed successfully
                        # Add your business logic here (e.g., activate subscription, send email)
                        self.handle_payment_success(payment, challenge, user)
                    elif data['payment_status'] == 'failed':
                        # Payment failed
                        # Add your business logic here
                        self.handle_payment_failure(payment)
                    elif data['payment_status'] == 'expired':
                        # Payment expired
                        self.handle_payment_expired(payment)
                
                return Response({'status': 'ok'})
                
            except Payment.DoesNotExist:
                return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response(
                {'error': 'Internal server error'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def handle_payment_success(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle successful payment"""
        first_name, last_name = split_full_name(user.full_name)
        address = Address.objects.get(user=user)

        balance = float(challenge.account_size)
        if challenge.challenge_class == 'skill_check':
            balance = float(challenge.account_size - (challenge.account_size * 0.1)) 

        print("Attempt creating MT5Account")
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
                'challenge_id': challenge.id,
                'competition_id': None,
            }
        )

        # send_bridge_test_req(settings.BRIDGE_URL)

        try:
            mailer = Mailer(user.email)
            mailer.payment_successful(user, challenge, payment)

            if result:
                mt5_user_login, password = result
                mt5_user = MT5User.objects.filter(login=mt5_user_login).first()
                if mt5_user:
                    mt5_user.refundable_fee = challenge.challenge_fee
                    mt5_user.user = user
                    mt5_user.challenge = challenge
                    mt5_user.password = encrypt_password(password)
                    mt5_user.save()
                    #Create Account Earning
                    target_profit_amount = (challenge.profit_target_percent / Decimal(100)) * challenge.account_size
                    AccountEarnings.objects.get_or_create(login=mt5_user.login, target=target_profit_amount)
                    #Send email
                    mailer.challenge_entry(mt5_user, challenge, password)

                    print("Account created:", mt5_user_login, password)
            else:
                print("Failed to create account")

            referral = Referral.objects.filter(user=user)
            if referral.exists():
                referral=referral.first()
                award_referral_reward(referral, challenge.challenge_fee)
            # logger.info(f"Payment {payment.order_id} completed and account {mt5_user.login} created")
        except Exception as err:
            pass

    
    def handle_payment_failure(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle failed payment - override this method for custom logic"""
        try:
            Mailer(user.email).payment_failed(user, challenge, payment)
            print(f"Payment {payment.order_id} failed")
        except Exception as err:
            print(f"Error while sending payment failure email: {str(err)}")
    
    def handle_payment_expired(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle expired payment - override this method for custom logic"""
        try:
            Mailer(user.email).payment_expired(user, challenge, payment)
            print(f"Payment {payment.order_id} expired")
        except Exception as err:
            print(f"Error while sending payment session timeout email: {str(err)}")




@method_decorator(csrf_exempt, name='dispatch')
class ContestPaymentIPNAPIView(APIView):
    """Handle IPN callbacks from NOWPayments"""
    permission_classes = []  # No authentication required for IPN
    
    def post(self, request):
        try:
            # Verify signature
            # signature = request.headers.get('x-nowpayments-sig')
            # if not signature:
            #     return Response({'error': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            service = NOWPaymentsService()
            # if not service.verify_ipn_signature(request.body, signature):
            #     return Response({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
            print("Payment IPN received")
            # Parse callback data
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Update payment status
            try:
                _, contest_id, user_id = data['order_id'].split('-')
                contest = get_object_or_404(Competition, id=contest_id)
                user = get_object_or_404(User, id=user_id)

                payment = Payment.objects.get(order_id=data['order_id'])
                old_status = payment.payment_status

                print("Payment Status", data['payment_status'])
                if old_status != data['payment_status']:
                    payment.payment_status = data['payment_status']
                    if 'pay_amount' in data:
                        payment.pay_amount = data['pay_amount']
                    payment.save()
                    
                    # Handle different payment statuses
                    if data['payment_status'] == 'finished':
                        # Payment completed successfully
                        # Add your business logic here (e.g., activate subscription, send email)
                        self.handle_payment_success(payment, contest, user)
                    elif data['payment_status'] == 'failed':
                        # Payment failed
                        # Add your business logic here
                        self.handle_payment_failure(payment)
                    elif data['payment_status'] == 'expired':
                        # Payment expired
                        self.handle_payment_expired(payment)
                
                return Response({'status': 'ok'})
                
            except Payment.DoesNotExist:
                return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            return Response(
                {'error': 'Internal server error'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def handle_payment_success(self, payment: Payment, contest: Competition, user):
        """Handle successful payment"""
        first_name, last_name = split_full_name(user.full_name)
        address = Address.objects.get(user=user)

        balance = float(contest.starting_balance)

        print("Attempt creating MT5Account")
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
            'comment': f"{settings.GLOBAL_SERVICE_NAME} Competition Account ({contest.name})",
            'challenge_name': contest.name,
            'challenge_id': None,
            'competition_id': contest.id
        }
        result = create_mt5_account(
            base_url=settings.BRIDGE_URL,
            account_data=account_data,
        )

        # result = send_bridge_test_req(settings.BRIDGE_URL, account_data)

        try:
            mailer = Mailer(user.email)
            mailer.contest_payment_successful(user, contest, payment)

            if result:
                mt5_user_login, password = result
                mt5_user = MT5User.objects.filter(login=mt5_user_login).first()
                if mt5_user:
                    mt5_user.user = user
                    mt5_user.competition = contest
                    mt5_user.password = encrypt_password(password)
                    mt5_user.account_type = 'competition'
                    mt5_user.save()
                    #Create Account Earning
                    AccountEarnings.objects.get_or_create(login=mt5_user.login)
                    # Send email
                    mailer.contest_entry(mt5_user, contest, password)

                    print("Account created:", mt5_user_login, password)
            else:
                print("Failed to create account")

            print(f"Payment {payment.order_id} completed and account {mt5_user.login} created")
        except Exception as err:
            pass

    
    def handle_payment_failure(self, payment: Payment, contest: Competition, user):
        """Handle failed payment - override this method for custom logic"""
        try:
            Mailer(user.email).contest_payment_failed(user, contest, payment)
            print(f"Payment {payment.order_id} failed")
        except Exception as err:
            print(f"Error while sending payment failure email: {str(err)}")
    
    def handle_payment_expired(self, payment: Payment, contest: Competition, user):
        """Handle expired payment - override this method for custom logic"""
        try:
            Mailer(user.email).contest_payment_expired(user, contest, payment)
            print(f"Payment {payment.order_id} expired")
        except Exception as err:
            print(f"Error while sending payment session timeout email: {str(err)}")






class PaystackPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        payload = request.data.copy()
        challenge_id = payload.pop('challenge_id', 0)
        platform = payload.pop('platform', 'mt5')
        challenge =  get_object_or_404(PropFirmChallenge, id=challenge_id)

        payload['amount'] = challenge.challenge_fee
        serializer = TransactionCreateSerializer(data=payload)
        
        if not serializer.is_valid():
            return Response({
                'success': False,
                'errors': str(next(iter(serializer.errors.values()))[0])
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Generate unique reference
            reference = f"txn_{uuid.uuid4().hex[:12]}"
            
            # Create transaction record
            transaction = Transaction.objects.create(
                user=request.user,
                reference=reference,
                amount=serializer.validated_data['amount'],
                payment_method=serializer.validated_data['payment_method']
            )
            
            # Initialize with Paystack
            paystack = PaystackService()
            frontend_url = request.META.get('HTTP_ORIGIN', 'http://localhost:5173')
            callback_url = f"{frontend_url}/dashboard?reference={reference}"
            
            metadata = {
                'user_id': request.user.id,
                'transaction_id': str(transaction.id),
                'payment_method': serializer.validated_data['payment_method'],
                'challenge_id': challenge.id,
                'platform': platform,
            }
            
            result = paystack.initialize_transaction(
                email=request.user.email,
                amount=serializer.validated_data['amount'],
                reference=reference,
                payment_method=serializer.validated_data['payment_method'],
                callback_url=callback_url,
                metadata=metadata
            )
            
            if result.get('status'):
                data = result.get('data', {})
                transaction.paystack_reference = data.get('reference')
                transaction.authorization_url = data.get('authorization_url')
                transaction.access_code = data.get('access_code')
                transaction.save()
                
                return Response({
                    'success': True,
                    'authorization_url': data.get('authorization_url')
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                return Response({
                    'success': False,
                    'message': result.get('message', 'Payment initialization failed')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class PaystackVerificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, reference):
        try:
            transaction = get_object_or_404(Transaction, reference=reference, user=request.user)
            
            # Verify with Paystack
            paystack = PaystackService()
            result = paystack.verify_transaction(reference)
            
            if result.get('status') and result.get('data'):
                data = result['data']
                
                if data.get('status') == 'success':
                    transaction.status = 'success'
                else:
                    transaction.status = 'failed'
            else:
                transaction.status = 'failed'
            
            transaction.save()
            
            serializer = TransactionSerializer(transaction)
            return Response({
                'success': True,
                'data': serializer.data
            })

        except Transaction.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Transaction not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class PaystackWebhookView(APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):      
        signature_header = request.headers.get('x-paystack-signature') 

        try:
            payload = request.data
            event = payload.get('event')
            data = payload.get('data', {})
            
            with open("logs/paystack_webhook_log.json", "w") as f:
                f.write(json.dumps(payload, indent=2))
                f.write("\n\n")  # For spacing between logs

            # Handle event
            reference = data.get('reference')
            meta = data.get('metadata', {})

            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}  # Default to empty dict if error
            
            challenge_id = meta.get('challenge_id', 0)
            platform = meta.get('platform', 'mt5')
            challenge = get_object_or_404(PropFirmChallenge, id=challenge_id)
            if reference:
                try:
                    transaction = Transaction.objects.get(reference=reference)
                    if transaction.status != 'pending':
                        return Response({'status': 'success'}, status=status.HTTP_200_OK)
                    
                    user = transaction.user

                    if event == 'charge.success':
                        idx = str(random.randint(100000, 999999))
                        transaction.status = 'success'
                        
                        award_referral_reward(user.referral_profile, transaction.amount)

                        Mailer(user.email).payment_successful(challenge.challenge_fee, challenge)

                    elif event in ['charge.failed', 'charge.cancelled']:
                        transaction.status = 'failed'
                    transaction.save()
                except Transaction.DoesNotExist:
                    pass  # Optionally log this too
            
            return Response({'status': 'success'}, status=status.HTTP_200_OK)
            
        except Exception as e:
            print(str(e))
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        


class PropFirmWalletView(APIView):
    serializer_class = PropFirmWalletSerializer
    permission_classes = [ permissions.IsAuthenticated, Is2FAEnabled]
    
    def get(self, request, *args, **kwargs):
        wallet, _ = PropFirmWallet.objects.get_or_create(user=request.user)
        data = self.serializer_class(wallet)
        return Response(data.data, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        user = request.user
        data = request.data.copy()

        # --- OTP check ---
        code = data.pop('code', None)
        if not code:
            return custom_response(
                status="Error",
                message="OTP code required!",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        # --- Ensure OTP secret exists ---
        if not getattr(user, "otp_secret", None):
            return custom_response(
                status="Error",
                message="OTP not configured for this account.",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )

        wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
        serializer = self.serializer_class(wallet, data=data, partial=True)

        if serializer.is_valid():
            # --- Verify OTP ---
            totp = pyotp.TOTP(user.otp_secret)
            if not totp.verify(code):
                return custom_response(
                    status="Error",
                    message="Invalid OTP code!",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            # --- Verify wallet via NOWPayments ---
            pay_address = serializer.validated_data.get('pay_address')
            pay_currency = serializer.validated_data.get('pay_currency')

            service = NOWPaymentsService()
            validity = service.verify_wallet_address(pay_address, pay_currency)

            if validity.get('success') is True:
                serializer.save()
                return custom_response(
                    status="success",
                    message="Details updated successfully.",
                    data=serializer.data,
                    http_status=status.HTTP_200_OK
                )

            error = validity.get("message", "Wallet address is invalid")
        else:
            error = next(iter(serializer.errors.values()))[0]

        return custom_response(
            status="Error",
            message=str(error),
            data={},
            http_status=status.HTTP_400_BAD_REQUEST
        )

class PropFirmWalletTransactionView(generics.ListAPIView):
    permission_classes = [ permissions.IsAuthenticated, Is2FAEnabled]
    serializer_class = PropFirmWalletTransactionSerializer
    filterset_class = PropFirmWalletTransactionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination

    @require_account_owner
    def get(self, request, login, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        login = self.kwargs.get('login')
        user = self.request.user
        get_object_or_404(MT5User, user=user, login=login)
        wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
        queryset = PropFirmWalletTransaction.objects.filter(wallet=wallet, login=login).order_by('-id')
        return queryset


class WithdrawalRequestHistory(generics.ListAPIView):
    permission_classes = [ permissions.IsAuthenticated, Is2FAEnabled]
    serializer_class = WithdrawalRequestSerializer
    filterset_class = WithdrawalRequestFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination

    @require_account_owner
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
    
    def get_queryset(self):
        login = self.kwargs.get("login")
        queryset = WithdrawalRequest.objects.filter(login=login).order_by("-created_at")
        return queryset


class WithdrawAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, Is2FAEnabled]

    @require_account_owner
    def post(self, request, login, *args, **kwargs):
        mt5_user: MT5User = request.mt5_user
        acc = get_object_or_404(MT5Account, mt5_user=mt5_user)

        starting_balance = mt5_user.challenge.account_size
        current_balance = acc.balance

        # --- Challenge type logic ---
        if mt5_user.challenge.challenge_class == "challenge":
            if not mt5_user.funded:
                return custom_response(
                    status="error",
                    message="You can only withdraw on a funded stage.",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN,
                )

            # 20% above starting balance required
            threshold = starting_balance * 1.2
            if current_balance < threshold:
                return custom_response(
                    status="error",
                    message="You can only withdraw when your balance is at least 20% above the starting balance.",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN,
                )

        elif mt5_user.challenge.challenge_class == "skill_check":
            if acc.step == 1:
                # 2% above starting balance required
                threshold = starting_balance * 1.02
                if current_balance < threshold:
                    return custom_response(
                        status="error",
                        message="You can only withdraw when your balance is at least 2% above the starting balance.",
                        data={},
                        http_status=status.HTTP_403_FORBIDDEN,
                    )
            elif not mt5_user.funded:
                return custom_response(
                    status="error",
                    message="You can only withdraw on a funded stage.",
                    data={},
                    http_status=status.HTTP_403_FORBIDDEN,
                )
        else:
            return custom_response(
                status="error",
                message="An error occurred while determining account type.",
                data={},
                http_status=status.HTTP_403_FORBIDDEN,
            )

        # --- Handle withdrawal request creation ---
        req, created = WithdrawalRequest.objects.get_or_create(login=login, status="pending")
        data = WithdrawalRequestSerializer(req).data

        if created:
            return custom_response(
                status="success",
                message="Withdrawal request submitted successfully. The admin will review it shortly.",
                data=data,
                http_status=status.HTTP_200_OK,
            )
        else:
            return custom_response(
                status="error",
                message="You already have a pending withdrawal request under review.",
                data=data,
                http_status=status.HTTP_403_FORBIDDEN,
            )




# class WalletFundingAPIView(APIView):
#     """Create a new payment"""
#     permission_classes = [permissions.IsAuthenticated]
    
#     def post(self, request):
#         user=request.user
#         payload = request.data.copy()
#         if payload.get('description', '') == '':
#             payload['description'] = f"Stanum wallet funding"

#         wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
#         serializer = PropFirmWalletTransactionCreateSerializer(data=payload)
#         if serializer.is_valid():

#             # Create payment record
#             order_id = f"STMWFD-{request.user.id}-{int(time.time())}{random.randint(100, 999)}"
#             transaction = PropFirmWalletTransaction.objects.create(
#                 wallet=wallet,
#                 order_id=order_id,
#                 type='credit',
#                 order_description=serializer.validated_data['description'],
#                 price_amount=serializer.validated_data['amount'],
#                 price_currency=serializer.validated_data['price_currency'],
#                 pay_currency=serializer.validated_data['currency']
#             )
            
#             # Create payment with NOWPayments
#             service = NOWPaymentsService()
#             ipn_url = request.build_absolute_uri('/api/v1/payment/wallet/fund/ipn')
            
#             result = service.create_payment(
#                 price_amount=serializer.validated_data['amount'],
#                 price_currency=serializer.validated_data['price_currency'],
#                 pay_currency=serializer.validated_data['currency'],
#                 order_id=order_id,
#                 order_description=serializer.validated_data['description'],
#                 ipn_callback_url=ipn_url
#             )
            
#             if 'error' in result:
#                 transaction.delete()  # Clean up failed payment
#                 return Response(
#                     {'error': result['error']}, 
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
            
#             # Update payment record with NOWPayments response
#             transaction.payment_id = result['payment_id']
#             transaction.pay_amount = result.get('pay_amount')
#             transaction.pay_address = result.get('pay_address')
#             transaction.save()
            
#             # Return created payment
#             response_serializer = PropFirmWalletTransactionSerializer(transaction)
#             return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
#         return custom_response(
#             status="error",
#             message = str(next(iter(serializer.errors.values()))[0]),
#             data=serializer.errors,
#             http_status=status.HTTP_403_FORBIDDEN
#         )
    


# @method_decorator(csrf_exempt, name="dispatch")
# class WalletFundingIPNAPIView(APIView):
#     """Webhook for NOWPayments IPN"""
#     authentication_classes = []
#     permission_classes = [permissions.AllowAny]

#     def post(self, request):
#         # Always capture raw body for debugging
#         try:
#             payload = json.loads(request.body)
#             print(f"Webhook received:\n{json.dumps(payload, indent=2)}")
#         except json.JSONDecodeError:
#             return Response({'error': 'Invalid JSON'}, status=status.HTTP_400_BAD_REQUEST)

#         payment_id = payload.get("payment_id")
#         payment_status = payload.get("payment_status")
#         pay_amount = payload.get("actually_paid")

#         if not payment_id:
#             print(f"Webhook missing payment_id: {payload}")
#             return Response({"error": "Missing payment_id"}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             transaction = PropFirmWalletTransaction.objects.get(payment_id=payment_id)
#         except PropFirmWalletTransaction.DoesNotExist:
#             print(f"Transaction not found for payment_id={payment_id}")
#             return Response({"error": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

#         print(f"Transaction {payment_id} updated with status {payment_status}")

#         if payment_status == "finished":
#             self.handle_success(transaction)
#         elif payment_status == "failed":
#             self.handle_payment_failure(transaction)
#         elif payment_status == "expired":
#             self.handle_payment_expired(transaction)

#         return Response({"message": "IPN processed"}, status=status.HTTP_200_OK)
    
#     def handle_success(self, transaction: PropFirmWalletTransaction):
#         wallet = transaction.wallet
#         user = wallet.user
#         wallet.withdrawal_profit += transaction.price_amount
#         wallet.save()
#         transaction.updated_at = timezone.now()
#         transaction.status = "completed"
#         transaction.save()
#         Mailer(user.email).wallet_funding_success(transaction)
#         print(f"Wallet {wallet.id} credited with {transaction.price_amount}")
    
#     def handle_payment_failure(self, transaction: PropFirmWalletTransaction):
#         wallet = transaction.wallet
#         user = wallet.user
#         transaction.updated_at = timezone.now()
#         transaction.status = "failed"
#         transaction.save()
#         Mailer(user.email).wallet_funding_failed(transaction)
#         print(f"Wallet {wallet.id} funding failed with {transaction.price_amount}")
    
#     def handle_payment_expired(self, transaction: PropFirmWalletTransaction):
#         wallet = transaction.wallet
#         user = wallet.user
#         transaction.updated_at = timezone.now()
#         transaction.status = "expired"
#         transaction.save()
#         print(f"Wallet {wallet.id} funding expired for {transaction.price_amount}")

# class ConfirmTransactionSuccess(APIView):
#     def get(self, request, *args, **kwargs):
#         id = request.query_params.get('id', 0)
#         trx = get_object_or_404(PropFirmWalletTransaction, id=id)
#         if trx.status == 'completed':
#             return custom_response(
#                 status='success',
#                 message='completed',
#                 data={"status": "completed"}
#             )
#         return custom_response(
#             status='error',
#             message=trx.status,
#             data={"status": trx.status},
#             http_status=status.HTTP_400_BAD_REQUEST
#         )