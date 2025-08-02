from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer, EstimateSerializer
from service.now_payment import NOWPaymentsService
from utils.mailer import Mailer
import json
import uuid

from challenge.models import *
from trading.models import *

User = get_user_model()

class AvailableCurrenciesAPIView(APIView):
    """Get list of available cryptocurrencies"""
    # authentication_classes = []
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
            payment = Payment.objects.create(
                user=request.user,
                order_id=order_id,
                order_description=serializer.validated_data['description'],
                price_amount=serializer.validated_data['amount'],
                price_currency=serializer.validated_data['price_currency'],
                pay_currency=serializer.validated_data['currency']
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
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PaymentListAPIView(ListAPIView):
    """List user's payments"""
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by('-created_at')

class PaymentDetailAPIView(RetrieveAPIView):
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
        Mailer(user.email).payment_successful(payment, challenge)
        print(f"Payment {payment.order_id} completed successfully")
    
    def handle_payment_failure(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle failed payment - override this method for custom logic"""
        Mailer(user.email).payment_failed(payment, challenge)
        print(f"Payment {payment.order_id} failed")
    
    def handle_payment_expired(self, payment: Payment, challenge: PropFirmChallenge, user):
        """Handle expired payment - override this method for custom logic"""
        Mailer(user.email).payment_expired(payment, challenge)
        print(f"Payment {payment.order_id} expired")