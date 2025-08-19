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

from asgiref.sync import async_to_sync

from challenge.models import *
from trading.models import *

from service.paystack import PaystackService
from service.metaapi_request import *
from utils.helper import *
from utils.permission import *
from utils.pagination import *
from utils.filters import *

User = get_user_model()

logger = logging.getLogger("webhook")

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
        if payload.get('description', '') == '':
            payload['description'] = f"Stanum payment"
        
        challenge_id = payload.get('challenge_id', '0')
        challenge = PropFirmChallenge.objects.filter(id=challenge_id)
        if challenge.exists():
            challenge = challenge.first()

        serializer = PaymentCreateSerializer(data=payload)
        if serializer.is_valid():

            # Create payment record
            order_id = f"STMCLG-{challenge.id}-{request.user.id}"
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
            ipn_url = request.build_absolute_uri('/api/payments/ipn/')
            
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
            signature = request.headers.get('x-nowpayments-sig')
            if not signature:
                return Response({'error': 'Missing signature'}, status=status.HTTP_400_BAD_REQUEST)
            
            service = NOWPaymentsService()
            if not service.verify_ipn_signature(request.body, signature):
                return Response({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
            
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
        """Handle successful payment - override this method for custom logic"""
        # Example: Send confirmation email, activate service, etc.
        account = TradingAccount.objects.create(
            user=user,
            challenge=challenge,
            metaapi_account_id="metaapi_12345678",
            login="123456",
            password="securepassword123",
            account_type="challenge",
            size=Decimal(challenge.account_size),
            server="MetaQuotes-Demo",
            leverage=100,
        )
        Mailer(user.email).payment_successful(challenge.challenge_fee, challenge)
        print(f"Payment {payment.order_id} completed successfully")
    
    def handle_payment_failure(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle failed payment - override this method for custom logic"""
        Mailer(user.email).payment_failed(challenge.challenge_fee, challenge)
        print(f"Payment {payment.order_id} failed")
    
    def handle_payment_expired(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle expired payment - override this method for custom logic"""
        Mailer(user.email).payment_expired(challenge.challenge_fee, challenge)
        print(f"Payment {payment.order_id} expired")



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
                        
                        index = TradingAccount.objects.all().count() + 1
                        mt5_account = async_to_sync(create_account)(
                            type='challenge',
                            index=index,
                            login='1234567',
                            password='abc123',
                            platform=platform
                        )

                        account = TradingAccount.objects.create(
                            user=user,
                            challenge=challenge,
                            metaapi_account_id=mt5_account.id,
                            login=idx,
                            password="securepassword123",
                            account_type="challenge",
                            size=Decimal(challenge.account_size),
                            server="MetaQuotes-Demo",
                            leverage=100,
                        )

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
        


class PropFirmWalletView(generics.RetrieveAPIView):
    serializer_class = PropFirmWalletSerializer
    permission_classes = [ permissions.IsAuthenticated, Is2FAEnabled]

    def get_object(self):
        user = self.request.user
        obj, _ = PropFirmWallet.objects.get_or_create(user=user)
        return obj
    

class PropFirmWalletTransactionView(generics.ListAPIView):
    serializer_class = PropFirmWalletTransactionSerializer
    filterset_class = PropFirmWalletTransactionFilter
    filter_backends = [DjangoFilterBackend]
    pagination_class = LargeResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
        queryset = PropFirmWalletTransaction.objects.filter(wallet=wallet).order_by('-id')
        return queryset


class WithdrawView(APIView):
    def post(self, request, *args, **kwargs):
        user = request.user
        payload = request.data
        service = NOWPaymentsService()

        try:
            # ✅ Enforce 2FA
            if not user.is_2fa_enabled:
                return custom_response(
                    status="Error",
                    message="You need to activate 2FA before making withdrawals.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            code = payload.get("code")
            currency_id = payload.get("currency_id")
            amount = Decimal(payload.get("amount", 0))
            wallet_address = payload.get("address")
            crypto_currency = payload.get("currency")
            crypto_network = payload.get("network")

            # ✅ Input validation
            if not code:
                return custom_response(
                    status="Error",
                    message="OTP code required!",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            if amount < Decimal("50"):
                return custom_response(
                    status="Error",
                    message="You cannot withdraw less than $50.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            if not wallet_address or not crypto_currency or not crypto_network:
                return custom_response(
                    status="Error",
                    message="Currency, network, and wallet address are required.",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Verify OTP
            totp = pyotp.TOTP(user.otp_secret)
            if not totp.verify(code):
                return custom_response(
                    status="Error",
                    message="Invalid OTP code!",
                    data={},
                    http_status=status.HTTP_400_BAD_REQUEST
                )

            # ✅ Verify wallet address format
            service.verify_wallet_address(wallet_address, crypto_currency)

            # ✅ Wrap in DB transaction to avoid race conditions
            with transaction.atomic():
                wallet = PropFirmWallet.objects.select_for_update().get(user=user)

                if wallet.withdrawal_profit < amount:
                    return custom_response(
                        status="Error",
                        message="Insufficient balance.",
                        data={},
                        http_status=status.HTTP_400_BAD_REQUEST
                    )

                # (Optional) Deduct immediately to block double spending
                wallet.withdrawal_profit -= amount
                wallet.pending_amount += amount
                wallet.save()

                # ✅ Create transaction as pending (disbursed_amount = 0)
                PropFirmWalletTransaction.objects.create(
                    wallet=wallet,
                    requested_amount=amount,
                    disbursed_amount=Decimal("0.00"),
                    status="pending",
                    type="debit",
                    currency_id=currency_id,
                    payout_currency=crypto_currency,
                    payout_network=crypto_network,
                    payout_wallet_address=wallet_address
                )

            return custom_response(
                status="success",
                message="Withdrawal request submitted. Admin will approve this payout shortly.",
                data={}
            )

        except PropFirmWallet.DoesNotExist:
            return custom_response(
                status="Error",
                message="Wallet not found.",
                data={},
                http_status=status.HTTP_404_NOT_FOUND
            )
        except Exception as err:
            logger.error(f"WITHDRAWAL REQUEST ERROR: {err}", exc_info=True)
            return custom_response(
                status="Error",
                message="Something went wrong while processing your withdrawal.",
                data={},
                http_status=status.HTTP_400_BAD_REQUEST
            )
        

class WalletFundingAPIView(APIView):
    """Create a new payment"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user=request.user
        payload = request.data.copy()
        if payload.get('description', '') == '':
            payload['description'] = f"Stanum wallet funding"

        wallet, _ = PropFirmWallet.objects.get_or_create(user=user)
        serializer = PropFirmWalletTransactionCreateSerializer(data=payload)
        if serializer.is_valid():

            # Create payment record
            order_id = f"STMWFD-{request.user.id}-{int(time.time())}{random.randint(100, 999)}"
            transaction = PropFirmWalletTransaction.objects.create(
                wallet=wallet,
                order_id=order_id,
                type='credit',
                order_description=serializer.validated_data['description'],
                price_amount=serializer.validated_data['amount'],
                price_currency=serializer.validated_data['price_currency'],
                pay_currency=serializer.validated_data['currency']
            )
            
            # Create payment with NOWPayments
            service = NOWPaymentsService()
            ipn_url = request.build_absolute_uri('/api/v1/payment/wallet/fund/ipn')
            
            result = service.create_payment(
                price_amount=serializer.validated_data['amount'],
                price_currency=serializer.validated_data['price_currency'],
                pay_currency=serializer.validated_data['currency'],
                order_id=order_id,
                order_description=serializer.validated_data['description'],
                ipn_callback_url=ipn_url
            )
            
            if 'error' in result:
                transaction.delete()  # Clean up failed payment
                return Response(
                    {'error': result['error']}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Update payment record with NOWPayments response
            transaction.payment_id = result['payment_id']
            transaction.pay_amount = result.get('pay_amount')
            transaction.pay_address = result.get('pay_address')
            transaction.save()
            
            # Return created payment
            response_serializer = PropFirmWalletTransactionSerializer(transaction)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        return custom_response(
            status="error",
            message = str(next(iter(serializer.errors.values()))[0]),
            data=serializer.errors,
            http_status=status.HTTP_403_FORBIDDEN
        )
    


@method_decorator(csrf_exempt, name="dispatch")
class WalletFundingIPNAPIView(APIView):
    """Webhook for NOWPayments IPN"""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Always capture raw body for debugging
        try:
            raw_body = request.body.decode("utf-8")
            print(f"Raw webhook body: {raw_body}")
            payload = request.data or json.loads(raw_body)
            print(f"Webhook received:\n{json.dumps(payload, indent=2)}")
        except Exception as e:
            print(f"Failed to parse webhook payload: {str(e)}")
            return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

        payment_id = payload.get("payment_id")
        payment_status = payload.get("payment_status")
        pay_amount = payload.get("actually_paid")

        if not payment_id:
            print(f"Webhook missing payment_id: {payload}")
            return Response({"error": "Missing payment_id"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            transaction = PropFirmWalletTransaction.objects.get(payment_id=payment_id)
        except PropFirmWalletTransaction.DoesNotExist:
            print(f"Transaction not found for payment_id={payment_id}")
            return Response({"error": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

        print(f"Transaction {payment_id} updated with status {payment_status}")

        if payment_status == "finished":
            self.handle_success(transaction)
        elif payment_status == "failed":
            self.handle_payment_failure(transaction)
        elif payment_status == "expired":
            self.handle_payment_expired(transaction)

        return Response({"message": "IPN processed"}, status=status.HTTP_200_OK)
    
    def handle_success(self, transaction: PropFirmWalletTransaction):
        wallet = transaction.wallet
        user = wallet.user
        wallet.withdrawal_profit += transaction.price_amount
        wallet.save()
        transaction.status = "completed"
        transaction.save()
        Mailer(user.email).wallet_funding_success(transaction)
        print(f"Wallet {wallet.id} credited with {transaction.price_amount}")
    
    def handle_payment_failure(self, transaction: PropFirmWalletTransaction):
        wallet = transaction.wallet
        user = wallet.user
        transaction.status = "failed"
        transaction.save()
        Mailer(user.email).wallet_funding_failed(transaction)
        print(f"Wallet {wallet.id} funding failed with {transaction.price_amount}")
    
    def handle_payment_expired(self, transaction: PropFirmWalletTransaction):
        wallet = transaction.wallet
        user = wallet.user
        transaction.status = "expired"
        transaction.save()
        print(f"Wallet {wallet.id} funding expired for {transaction.price_amount}")

class ConfirmTransactionSuccess(APIView):
    def get(self, request, *args, **kwargs):
        id = request.query_params.get('id', 0)
        trx = get_object_or_404(PropFirmWalletTransaction, id=id)
        if trx.status == 'completed':
            return custom_response(
                status='success',
                message='completed',
                data={"status": "completed"}
            )
        return custom_response(
            status='error',
            message=trx.status,
            data={"status": trx.status},
            http_status=status.HTTP_400_BAD_REQUEST
        )