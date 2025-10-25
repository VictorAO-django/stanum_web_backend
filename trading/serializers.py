from datetime import date
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *
from utils.helper import decrypt_password, average_winning_trade, average_losing_trade, calculate_profit_factor, calculate_win_ratio
from challenge.serializers import PropFirmChallengeSerializer

class MT5UserSerializer(serializers.ModelSerializer):
    challenge_name = serializers.SerializerMethodField()
    challenge_class = serializers.SerializerMethodField()
    free_margin = serializers.SerializerMethodField()
    net_profit = serializers.SerializerMethodField()
    account_size = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()
    password = serializers.SerializerMethodField()

    class Meta:
        model = MT5User
        fields = [
            'login', 'server', 'balance', 'account_type', 'account_status', 'password', 'created_at',
            'free_margin', 'net_profit', 'account_size', 'equity', 'challenge_name', 'challenge_class'
        ]

    def get_challenge_class(self, obj):
        if(obj.challenge):
            return obj.challenge.challenge_class
        return ""

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
    

class MT5PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MT5Position
        fields = ['login', 'position_id', 'symbol', 'action', 'volume', 'closed']

class AccountWaterMarksSerializer(serializers.ModelSerializer):
    class Meta:
        model=AccountWatermarks
        fields="__all__"

class DailyDrawdownSerializer(serializers.ModelSerializer):
    class Meta:
        model=AccountDrawdown
        fields=['login', "equity_high", "equity_low", "drawdown_percent", "created_at"]

class TotalDrawdownSerializer(serializers.ModelSerializer):
    class Meta:
        model=AccountTotalDrawdown
        fields=['login', "equity_peak", "equity_low", "drawdown_percent", "created_at"]


class AccountStatSerializer(serializers.ModelSerializer):
    challenge =  serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    avg_winning = serializers.SerializerMethodField()
    avg_losing = serializers.SerializerMethodField()
    profit_factor = serializers.SerializerMethodField()
    win_ratio = serializers.SerializerMethodField()
    watermarks = serializers.SerializerMethodField()
    violation_summary = serializers.SerializerMethodField()
    daily_drawdown = serializers.SerializerMethodField()
    total_drawdown = serializers.SerializerMethodField()
    class Meta:
        model = MT5Account
        fields = [
            'balance', 'equity', 'profit', 'created_at', 'avg_winning', 'avg_losing', 'profit_factor', 'win_ratio',
            'challenge', "step", 'failure_reason', "watermarks", "violation_summary", "daily_drawdown", "total_drawdown"
        ]

    def get_challenge(self, obj):
       return None
    
    def get_created_at(self, obj):
        return ""
    
    def get_violation_summary(self, obj):
        return 0
    
    def get_avg_winning(self, obj):
        return average_winning_trade(obj.login)
    
    def get_avg_losing(self, obj):
        return average_losing_trade(obj.login)
    
    def get_profit_factor(self, obj):
        pf = calculate_profit_factor(obj.login)
        return pf

    def get_win_ratio(self, obj):
        return calculate_win_ratio(obj.login)
    
    def get_watermarks(self, obj):
        return {}
    
    def get_daily_drawdown(self, obj):
        return {}
    
    def get_total_drawdown(self, obj):
        return {}
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user =  MT5User.objects.get(login=instance.login)
        representation['created_at'] = user.created_at
        representation['account_status'] = user.account_status
        if user.challenge:
            representation['challenge'] = PropFirmChallengeSerializer(user.challenge).data

        vio = RuleViolationLog.objects.filter(login=instance.login)
        representation["violation_summary"] = {
            "warning": vio.filter(severity='warning').count(),
            "severe": vio.filter(severity='severe').count(),
            "crititcal": vio.filter(severity='critical').count()
        }
        
        start_balance = (getattr(user.challenge, "account_size", None) or getattr(user.competition, "starting_balance", None) or 0)
        watermark, _ = AccountWatermarks.objects.get_or_create(login=instance.login, defaults={
            "hwm_balance": start_balance,
            "hwm_equity": start_balance,
            "lwm_balance": start_balance,
            "lwm_equity": start_balance,
        })
        representation['watermarks'] = AccountWaterMarksSerializer(watermark).data

        try:
            dd = AccountDrawdown.objects.filter(login=instance.login).latest()
        except AccountDrawdown.DoesNotExist:
            dd = AccountDrawdown.objects.create(login=instance.login, date=date.today())
        representation["daily_drawdown"] = DailyDrawdownSerializer(dd).data

        td, _ = AccountTotalDrawdown.objects.get_or_create(login=instance.login)
        representation["total_drawdown"] = TotalDrawdownSerializer(td).data

        return representation
    

class DailySummary(serializers.ModelSerializer):
    class Meta:
        model=MT5Daily
        fields=['login', 'balance', 'profit', 'datetime']



class AccountEarningsSerializer(serializers.ModelSerializer):
    balance = serializers.SerializerMethodField()
    current_profit = serializers.SerializerMethodField()
    class Meta:
        model=AccountEarnings
        fields = ['login', 'balance', 'current_profit', 'pending', 'disbursed', 'target', 'paid_all']
    
    def get_balance(self, obj):
        acc = MT5Account.objects.filter(login=obj.login).first()
        if acc:
            return acc.balance
        return 0
    
    def get_current_profit(self, obj):
        return 0

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        acc = MT5Account.objects.filter(login=instance.login).first()
        user = MT5User.objects.filter(login=instance.login).first()
        start_balance = (getattr(user.challenge, "account_size", None) or getattr(user.competition, "starting_balance", None) or 0)
        if acc and user:
            representation['balance'] = acc.balance
            profit = acc.balance - start_balance
            if profit > 0:
                representation['current_profit'] = acc.balance - start_balance
        
        return representation




class RuleViolationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleViolationLog
        fields = ['id', 'login', 'violation_type', 'severity', 'message', 'timestamp']


class ChallengeLogSerializer(serializers.ModelSerializer):
    login = serializers.CharField(source='user.login', read_only=True)
    class Meta:
        model = ChallengeLog
        fields = ['id', 'login', 'action', 'details', 'timestamp']