# serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import *
from utils.helper import decrypt_password, average_winning_trade, average_losing_trade
from challenge.serializers import PropFirmChallengeSerializer

class MT5UserSerializer(serializers.ModelSerializer):
    challenge_name = serializers.SerializerMethodField()
    free_margin = serializers.SerializerMethodField()
    net_profit = serializers.SerializerMethodField()
    account_size = serializers.SerializerMethodField()
    equity = serializers.SerializerMethodField()
    password = serializers.SerializerMethodField()
    class Meta:
        model = MT5User
        fields = [
            'login', 'server', 'balance', 'account_type', 'account_status', 'password', 'created_at',
            'free_margin', 'net_profit', 'account_size', 'equity', 'challenge_name'
        ]

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
        return "0.0000"
    
    def get_free_margin(self, obj):
        return "0.0000"
    
    def get_net_profit(self, obj):
        return "0.0000"
    
    def get_equity(self, obj):
        return "0.0000"
    
    def to_representation(self, instance):
        representation =  super().to_representation(instance)
        account = MT5Account.objects.filter(login=instance.login)
        if account.exists():
            account = account.first()
            representation['free_margin'] = account.margin_free
            representation['net_profit'] = account.profit
            representation['equity'] = account.equity
        return super().to_representation(instance)
    

class MT5PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MT5Position
        fields = ['login', 'position_id', 'symbol', 'action', 'volume', 'closed']

class AccountStatSerializer(serializers.ModelSerializer):
    challenge =  serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()
    warning =  serializers.SerializerMethodField()
    critical =  serializers.SerializerMethodField()
    severe =  serializers.SerializerMethodField()
    avg_winning = serializers.SerializerMethodField()
    avg_losing = serializers.SerializerMethodField()

    class Meta:
        model = MT5Account
        fields = [
            'balance', 'equity', 'profit', 'created_at', 'warning', 'critical', 'severe', 'avg_winning', 'avg_losing',
            'challenge', 
        ]

    def get_challenge(self, obj):
       return []
    
    def get_created_at(self, obj):
        return ""
    
    def get_warning(self, obj):
        return 0
    
    def get_critical(self, obj):
        return 0
    
    def get_severe(self, obj):
        return 0
    
    def get_avg_winning(self, obj):
        return average_winning_trade(obj.login)
    
    def get_avg_losing(self, obj):
        return average_losing_trade(obj.login)
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user =  MT5User.objects.get(login=instance.login)
        representation['created_at'] = user.created_at
        representation['challenge'] = PropFirmChallengeSerializer(user.challenge).data

        vio = RuleViolationLog.objects.filter(login=instance.login)
        representation['warning'] = vio.filter(severity='warning').count()
        representation['severe'] = vio.filter(severity='severe').count()
        representation['critical'] = vio.filter(severity='critical').count()
        return representation
    

class DailySummary(serializers.ModelSerializer):
    class Meta:
        model=MT5Daily
        fields=['login', 'balance', 'profit', 'datetime']