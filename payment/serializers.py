from rest_framework import serializers
from .models import Payment

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