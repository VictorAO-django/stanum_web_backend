from rest_framework import serializers
from account.models import *
from challenge.models import *
from payment.models import *
from trading.models import *

class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    class Meta:
        model=User
        fields=['id', 'full_name', 'email', 'date_joined', 'last_login', 'role']

    def get_role(self, obj):
        role = 'admin' if obj.is_superuser else 'user'
        return role
    
class ChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model=PropFirmChallenge
        fields = [
            "id", "name", "firm_name", "description", "challenge_type", "status", "account_size", "challenge_fee", 
            "refundable_fee", "profit_split_percent", "max_daily_loss_percent", "max_total_loss_percent", 
            "profit_target_percent", "min_trading_days", "max_trading_days", "consistency_rule_percent", 
            "weekend_holding", "news_trading_allowed", "ea_allowed", "copy_trading_allowed", "allowed_instruments", 
            "duration_days", "max_participants", "current_participants", "created_at", "updated_at"
        ]

class HomeAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = '__all__'

class AddressProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProofOfAddress
        fields = '__all__'

class IDProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProofOfIdentity 
        fields = '__all__'

class UserKYCDataSerializer(serializers.ModelSerializer):
    address = HomeAddressSerializer(read_only=True)
    address_proof = AddressProofSerializer(source='kyc_address', many=True, read_only=True)
    id_proof = IDProofSerializer(source='kyc_identity', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'full_name', 'email', 'address', 'address_proof', 'id_proof']

class UserDetailSerializer(serializers.ModelSerializer):
    address = HomeAddressSerializer(read_only=True)
    class Meta:
        model=User
        fields=[
            'id', 'full_name', 'email', 'date_of_birth', 'phone_number', 'country', 'address'
        ]

class UserWalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropFirmWallet
        fields = ['id', 'wallet_id', 'withdrawal_profit', 'pending_amount', 'disbursed_amount']


class UserWalletTransactionSerializer(serializers.ModelSerializer):
    qr_code_url = serializers.SerializerMethodField()
    user = UserDetailSerializer(source='wallet.user', read_only=True)
    class Meta:
        model = PropFirmWalletTransaction
        fields = [
            'id', 'transaction_id', 'pay_amount', 'disbursed_amount', 'type',
            'pay_currency', 'pay_address', 'pay_network', 'qr_code_url', 'price_amount', 
            'price_currency', 'payment_id', 'status', 'created_at', 'user'
        ]

    def get_qr_code_url(self, obj):
        if obj.pay_address:
            return f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={obj.pay_address}"
        return None
    

class TradingAccountSerializer(serializers.ModelSerializer):
    challenge = ChallengeSerializer(read_only=True)
    class Meta:
        model = TradingAccount
        fields = [
            'id', 'user', 'challenge', 'metaapi_account_id', 'login', 'password', 'account_type', 'size', 'status', 'server',
            'leverage', 'balance', 'equity', 'margin', 'free_margin', 'margin_level', 'risk_daily_loss_limit', 'risk_max_drawdown',
            'risk_profit_target', 'max_daily_trades', 'disable_reason', 'disabled_at', 'completed_at',
            'selected_date', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']