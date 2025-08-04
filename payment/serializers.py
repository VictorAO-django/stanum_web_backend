from rest_framework import serializers
from .models import *

class PaymentCreateSerializer(serializers.Serializer):
    challenge_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2, min_value=0.01)
    currency = serializers.CharField(max_length=10)
    description = serializers.CharField(max_length=500, required=False, default='Payment')
    price_currency = serializers.CharField(max_length=10, default='USD')


class PaymentSerializer(serializers.ModelSerializer):
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    qr_code_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Payment
        fields = [
            'id', 'order_id', 'order_description', 'price_amount', 
            'price_currency', 'pay_currency', 'pay_amount', 'pay_address',
            'payment_status', 'payment_status_display', 'payment_id',
            'created_at', 'updated_at', 'qr_code_url'
        ]
        read_only_fields = ['id', 'payment_id', 'pay_amount', 'pay_address', 'created_at', 'updated_at']
    
    def get_qr_code_url(self, obj):
        if obj.pay_address:
            return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={obj.pay_address}"
        return None

class EstimateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency_from = serializers.CharField(max_length=10, default='USD')
    currency_to = serializers.CharField(max_length=10)


class TransactionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['amount', 'payment_method']
        
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero")
        return value
    
    def validate_payment_method(self, value):
        valid_methods = [choice[0] for choice in Transaction.PAYMENT_METHODS]
        if value not in valid_methods:
            raise serializers.ValidationError("Invalid payment method")
        return value
    

class TransactionSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Transaction
        fields = [
            'id', 'reference', 'amount', 'currency', 
            'payment_method', 'payment_method_display', 'status', 
            'status_display', 'paystack_reference', 'authorization_url', 
            'access_code', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'reference', 'paystack_reference', 
            'authorization_url', 'access_code', 'created_at', 'updated_at'
        ]