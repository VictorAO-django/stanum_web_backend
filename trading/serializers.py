# serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    TradingAccount, Trade, AccountActivity, 
    DailyAccountStats, UserProfile
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class UserProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    challenge_pass_rate = serializers.ReadOnlyField()
    can_create_challenge = serializers.SerializerMethodField()
    can_create_funded = serializers.SerializerMethodField()
    
    class Meta:
        model = UserProfile
        fields = [
            'user', 'phone_number', 'country', 'tier', 'years_experience',
            'max_challenge_accounts', 'max_funded_accounts', 'subscription_active',
            'subscription_expires', 'total_challenges_attempted', 'challenges_passed',
            'total_profit_earned', 'challenge_pass_rate', 'can_create_challenge',
            'can_create_funded', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'challenge_pass_rate']
    
    def get_can_create_challenge(self, obj):
        return obj.can_create_challenge_account()
    
    def get_can_create_funded(self, obj):
        return obj.can_create_funded_account()


class TradeSerializer(serializers.ModelSerializer):
    total_result = serializers.ReadOnlyField()
    duration = serializers.ReadOnlyField()
    
    class Meta:
        model = Trade
        fields = [
            'id', 'position_id', 'order_id', 'symbol', 'type', 'volume',
            'open_price', 'current_price', 'close_price', 'stop_loss', 'take_profit',
            'profit', 'swap', 'commission', 'total_result', 'status', 'open_time',
            'close_time', 'duration', 'comment', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'position_id', 'order_id', 'current_price', 'close_price', 
            'profit', 'swap', 'commission', 'total_result', 'status', 'close_time',
            'duration', 'created_at', 'updated_at'
        ]


class AccountActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountActivity
        fields = [
            'id', 'activity_type', 'description', 'timestamp', 'metadata'
        ]
        read_only_fields = ['id', 'timestamp']


class DailyAccountStatsSerializer(serializers.ModelSerializer):
    win_rate = serializers.ReadOnlyField()
    profit_factor = serializers.ReadOnlyField()
    
    class Meta:
        model = DailyAccountStats
        fields = [
            'id', 'date', 'starting_balance', 'starting_equity', 'highest_equity',
            'lowest_equity', 'ending_equity', 'trades_count', 'winning_trades',
            'losing_trades', 'daily_pnl', 'gross_profit', 'gross_loss',
            'max_drawdown_pct', 'daily_loss_pct', 'win_rate', 'profit_factor',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'win_rate', 'profit_factor', 'created_at', 'updated_at'
        ]


class TradingAccountSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    is_active = serializers.ReadOnlyField()
    daily_loss_limit_amount = serializers.ReadOnlyField()
    max_drawdown_amount = serializers.ReadOnlyField()
    recent_trades = TradeSerializer(many=True, read_only=True, source='trades')
    recent_activities = AccountActivitySerializer(many=True, read_only=True, source='activities')
    
    class Meta:
        model = TradingAccount
        fields = [
            'id', 'user', 'metaapi_account_id', 'login', 'account_type', 'status',
            'server', 'leverage', 'balance', 'equity', 'margin', 'free_margin',
            'margin_level', 'risk_daily_loss_limit', 'risk_max_drawdown',
            'risk_profit_target', 'max_daily_trades', 'disable_reason',
            'disabled_at', 'completed_at', 'is_active', 'daily_loss_limit_amount',
            'max_drawdown_amount', 'recent_trades', 'recent_activities',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'metaapi_account_id', 'login', 'balance', 'equity', 'margin',
            'free_margin', 'margin_level', 'disable_reason', 'disabled_at',
            'completed_at', 'is_active', 'daily_loss_limit_amount',
            'max_drawdown_amount', 'recent_trades', 'recent_activities',
            'created_at', 'updated_at'
        ]
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Limit recent trades and activities to latest 10
        if 'recent_trades' in data:
            data['recent_trades'] = data['recent_trades'][:10]
        if 'recent_activities' in data:
            data['recent_activities'] = data['recent_activities'][:10]
        return data


class AccountCreateRequestSerializer(serializers.Serializer):
    """Serializer for MetaAPI account creation requests"""
    account_type = serializers.ChoiceField(choices=['challenge', 'funded'])
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, default=100000)
    name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    server = serializers.CharField(max_length=100, default="MetaQuotes-Demo")
    leverage = serializers.IntegerField(default=100, min_value=1, max_value=1000)
    
    def validate_account_type(self, value):
        """Validate account type based on user permissions"""
        user = self.context['request'].user
        profile = getattr(user, 'trading_profile', None)
        
        if not profile:
            raise serializers.ValidationError("User profile not found")
        
        if value == 'challenge' and not profile.can_create_challenge_account():
            raise serializers.ValidationError(
                f"Maximum challenge accounts ({profile.max_challenge_accounts}) reached"
            )
        
        if value == 'funded' and not profile.can_create_funded_account():
            raise serializers.ValidationError(
                f"Maximum funded accounts ({profile.max_funded_accounts}) reached"
            )
        
        return value
    
    def validate_balance(self, value):
        """Validate balance based on account type"""
        account_type = self.initial_data.get('account_type')
        
        if account_type == 'challenge':
            if value < 10000 or value > 200000:
                raise serializers.ValidationError(
                    "Challenge account balance must be between $10,000 and $200,000"
                )
        elif account_type == 'funded':
            if value < 25000 or value > 2000000:
                raise serializers.ValidationError(
                    "Funded account balance must be between $25,000 and $2,000,000"
                )
        
        return value


class TradeRequestSerializer(serializers.Serializer):
    """Serializer for trade execution requests"""
    symbol = serializers.CharField(max_length=20)
    action = serializers.ChoiceField(choices=['buy', 'sell'])
    volume = serializers.DecimalField(max_digits=10, decimal_places=5, min_value=0.01)
    stop_loss = serializers.DecimalField(max_digits=15, decimal_places=5, required=False, allow_null=True)
    take_profit = serializers.DecimalField(max_digits=15, decimal_places=5, required=False, allow_null=True)
    comment = serializers.CharField(max_length=255, required=False, allow_blank=True)
    
    def validate_volume(self, value):
        """Validate trade volume"""
        if value > 100:  # Maximum 100 lots
            raise serializers.ValidationError("Maximum volume is 100 lots")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        symbol = data.get('symbol')
        action = data.get('action')
        stop_loss = data.get('stop_loss')
        take_profit = data.get('take_profit')
        
        # Validate symbol format (basic validation)
        if not symbol or len(symbol) < 6:
            raise serializers.ValidationError("Invalid symbol format")
        
        # Validate stop loss and take profit logic (simplified)
        if stop_loss and take_profit:
            if action == 'buy':
                if stop_loss >= take_profit:
                    raise serializers.ValidationError(
                        "For buy orders, stop loss must be less than take profit"
                    )
            elif action == 'sell':
                if stop_loss <= take_profit:
                    raise serializers.ValidationError(
                        "For sell orders, stop loss must be greater than take profit"
                    )
        
        return data


class AccountStatusSerializer(serializers.Serializer):
    """Serializer for account status response from MetaAPI service"""
    success = serializers.BooleanField()
    account_id = serializers.CharField()
    real_time = serializers.DictField()
    daily_stats = serializers.DictField()
    positions = serializers.ListField()
    
    class Meta:
        fields = ['success', 'account_id', 'real_time', 'daily_stats', 'positions']


class MetaAPIResponseSerializer(serializers.Serializer):
    """Generic serializer for MetaAPI service responses"""
    success = serializers.BooleanField()
    message = serializers.CharField(required=False)
    
    class Meta:
        fields = ['success', 'message']