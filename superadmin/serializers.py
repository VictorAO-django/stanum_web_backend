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
        fields = ['id', 'wallet_id', 'currency_id', 'pay_network', 'pay_address', 'pay_currency']


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
    account_size = serializers.SerializerMethodField()
    name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    balance = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    funded_eligible = serializers.SerializerMethodField()
    funded = serializers.SerializerMethodField()
    class Meta:
        model = MT5User
        fields = [
            'login', 'balance', 'created_at', 'email', 'account_size',
            "name", "is_active", "balance", "funded_eligible", "funded"
        ]
    
    def get_account_size(self, obj):
        if obj.challenge:
            return obj.challenge.account_size
        return 0.0000
    
    def get_funded_eligible(self, obj):
        return False
    
    def get_funded(self, obj):
        return False
    
    def get_is_active(self, obj):
        return False
    
    def get_balance(self, obj):
        return 0.0
    
    def to_representation(self, instance):
        representation =  super().to_representation(instance)
        account = MT5Account.objects.filter(login=instance.login)
        # print("Got account instancr", account)
        if account.exists():
            account = account.first()
            representation['balance'] = account.balance
            representation['funded_eligible'] = account.is_funded_eligible
            representation['funded'] = account.funded
            representation['is_active'] = account.active
        return representation
    

class AdminMT5AccountSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    challenge_name = serializers.SerializerMethodField()
    account_size = serializers.SerializerMethodField()
    positions = serializers.SerializerMethodField()
    class Meta:
        model=MT5Account
        fields = ["login", "name", "email", "step", "balance", "equity", "challenge_name", "account_size", "positions"]
    
    def get_name(self, obj):
        return ""
    
    def get_email(self, obj):
        return ""
    
    def get_challenge_name(self, obj):
        return ""
    
    def get_account_size(self, obj):
        return 0.0000
    
    def get_positions(self, obj):
        positions = MT5Position.objects.filter(login=obj.login, closed=False)
        return positions.count()
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        mt5_user = MT5User.objects.filter(login=instance.login)
        if mt5_user.exists():
            mt5_user = mt5_user.first()
            challenge= mt5_user.challenge
            if mt5_user.user:
                representation['name'] = mt5_user.user.full_name
                representation["email"] = mt5_user.user.email
            if challenge:
                representation["account_size"] = challenge.account_size
                representation['challenge_name'] = challenge.name
        return representation


class AdminMT5PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MT5Position
        fields = ["login", "symbol", "action", "price_open", "price_current", "volume", "profit"]


class CompetitionStatusSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    contestants = serializers.SerializerMethodField()
    class Meta:
        model = Competition
        fields = ["id", "starting_balance", "is_active", "start_date", "end_date", "contestants"]

    def get_is_active(self, obj):
        return obj.is_active()
    
    def get_contestants(self, obj):
        mt5_users = MT5User.objects.filter(competition=obj)
        return mt5_users.count()

class ChallengeLogSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.user.full_name")
    class Meta:
        model = ChallengeLog
        fields = ["id", "name", "timestamp", "details", "action"]


class AdminCompetitionSerializer(serializers.ModelSerializer):
    contestants = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    contest_link = serializers.SerializerMethodField()
    class Meta:
        model=Competition
        fields=["id", "name", "description", "contestants", "starting_balance", "price_pool_cash", "start_date", "end_date", "prize_structure", "contest_link", "is_active"]

    def get_is_active(self, obj):
        return obj.ended
    
    def get_contestants(self, obj):
        mt5_users = MT5User.objects.filter(competition=obj)
        return mt5_users.count()
    
    def get_contest_link(self, obj):
        return f"{settings.FRONTEND_BASE_URL}/contest/{obj.uuid}"
    

class CreateCompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model=Competition
        fields=["id", "name", "description", "starting_balance", "price_pool_cash", "prize_structure", "start_date", "end_date"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["contest_link"] = f"{settings.FRONTEND_BASE_URL}/contest/{instance.uuid}"
        return representation
    

class CompetitionStatSerializer(serializers.ModelSerializer):
    return_percent = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    trader_name = serializers.SerializerMethodField()
    rank=serializers.SerializerMethodField()
    profit=serializers.SerializerMethodField()
    losing_trade=serializers.SerializerMethodField()
    winning_trade=serializers.SerializerMethodField()
    win_rate=serializers.SerializerMethodField()

    class Meta:
        model=MT5User
        fields = ["login", "return_percent", "score", "profit", "trader_name", "rank", "win_rate", "losing_trade", "winning_trade"]
    
    def get_return_percent(self, obj):
        0

    def get_profit(self, obj):
        return 0
    
    def get_score(self, obj):
        return 0
    
    def get_trader_name(self, obj):
        full_name = (obj.user.full_name or '').strip()
        return full_name if full_name else f"Trader {obj.login}"
    
    def get_rank(self, obj):
        return 0
    
    def get_profit(self, obj):
        return 0
    
    def get_losing_trade(self, obj):
        return 0

    def get_winning_trade(self, obj):
        return 0
    
    def get_win_rate(self, obj):
        return 0
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)

        competition: Competition = instance.competition
        starting_balance = competition.starting_balance or Decimal("0")

        account = MT5Account.objects.filter(login=instance.login).first()
        if not account:
            # Return zeroed stats if account not found
            representation.update({
                "profit": Decimal("0"),
                "return_percent": Decimal("0"),
                "score": 0,
                "winning_trade": 0,
                "losing_trade": 0,
                "win_rate": Decimal("0"),
            })
            return representation

        # Compute profit and return %
        profit = account.balance - starting_balance
        return_percent = (profit / starting_balance * 100) if starting_balance > 0 else Decimal("0")

        # Compute trades
        positions = MT5Position.objects.filter(login=instance.login)
        winning = positions.filter(closed=True, profit__gt=0)
        losing = positions.filter(closed=True, profit__lte=0)

        win_rate = (
            (winning.count() / positions.count()) * 100
            if positions.exists()
            else Decimal("0")
        )

        # Compute drawdown score
        td, _ = AccountTotalDrawdown.objects.get_or_create(login=instance.login)
        score = float(return_percent) / (float(td.drawdown_percent) + 0.01)

        # Attach all to representation
        representation.update({
            "profit": profit,
            "return_percent": return_percent,
            "score": score,
            "winning_trade": winning.count(),
            "losing_trade": losing.count(),
            "win_rate": win_rate,
        })

        return representation