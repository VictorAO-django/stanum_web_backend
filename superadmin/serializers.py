from rest_framework import serializers
from account.models import *
from challenge.models import *
from payment.models import *
from trading.models import *
from utils.helper import *

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
            "refundable_fee", "profit_split_percent", "max_daily_loss_percent", "max_total_loss_percent", "challenge_class",
            "profit_target_percent", "min_trading_days", "max_trading_days", "additional_trading_days", "max_trades_per_minute", "max_trades_per_hour", 
            "consistency_rule_percent", "cross_account_hedging_allowed", "hedging_within_account_allowed", "martingale_allowed",
            "grid_trading_allowed", "statistical_arbitrage_allowed", "market_making_allowed", "latency_arbitrage_allowed",
            "overall_risk_limit_percent", "max_orders_per_symbol", "max_risk_per_trade_percent","weekend_holding", 
            "news_trading_allowed", "ea_allowed", "copy_trading_allowed", "allowed_instruments", "duration_days", 
            "max_participants", "current_participants", "created_at", "updated_at", 
            
            "phase_2_profit_target_percent", "phase_2_min_trading_days", "phase_2_max_trading_days"
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
    


class AdminMT5UserSerializer(serializers.ModelSerializer):
    challenge_name = serializers.SerializerMethodField()
    challenge_class = serializers.CharField(source='challenge.challenge_class')
    free_margin = serializers.SerializerMethodField()
    net_profit = serializers.SerializerMethodField()
    account_size = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()
    password = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    user_id = serializers.SerializerMethodField()
    class Meta:
        model = MT5User
        fields = [
            'login', 'server', 'balance', 'account_type', 'account_status', 'password', 'created_at',
            'free_margin', 'net_profit', 'account_size', 'equity', 'challenge_name', 'challenge_class', 'email', 'user_id'
        ]
    
    def get_email(self, obj):
        if obj.user:
            return obj.user.email
        return ""
    
    def get_user_id(self, obj):
        if obj.user:
            return obj.user.id
        return 0
    
    def get_password(self, obj):
        if obj.password:
            return decrypt_password(obj.password)
        return ""
    
    def get_challenge_name(self, obj):
        if obj.challenge:
            return obj.challenge.name
        return ""
    
    def get_account_size(self, obj):
        if obj.challenge:
            return obj.challenge.account_size
        return 0.0000
    
    def get_free_margin(self, obj):
        return 0.0000
    
    def get_net_profit(self, obj):
        return 0.0000
    
    def get_equity(self, obj):
        return 0.0000
    
    def to_representation(self, instance):
        representation =  super().to_representation(instance)
        account = MT5Account.objects.filter(login=instance.login)
        # print("Got account instancr", account)
        if account.exists():
            account = account.first()
            representation['free_margin'] = account.margin_free
            representation['net_profit'] = account.profit
            representation['equity'] = account.equity
        return representation