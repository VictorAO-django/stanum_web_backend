from rest_framework import serializers
from .models import *
from django.utils import timezone
from trading.models import MT5User


class PropFirmChallengeSerializer(serializers.ModelSerializer):
    is_available = serializers.ReadOnlyField()
    spots_remaining = serializers.ReadOnlyField()
    
    class Meta:
        model = PropFirmChallenge
        fields = [
            'id',
            'name',
            'firm_name',
            'description',
            'challenge_type',
            'status',
            'account_size',
            'challenge_fee',
            'challenge_class',
            'refundable_fee',
            'profit_split_percent',
            'max_daily_loss_percent',
            'max_total_loss_percent',
            'profit_target_percent',
            'min_trading_days',
            'max_trading_days',
            'consistency_rule_percent',
            'weekend_holding',
            'news_trading_allowed',
            'ea_allowed',
            'copy_trading_allowed',
            'allowed_instruments',
            'duration_days',
            'max_participants',
            'current_participants',
            'is_available',
            'spots_remaining',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_available', 'spots_remaining']


class ChallengeCertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model=ChallengeCertificate
        fields=['challenge_class', 'name', 'account_size', 'profit']


class CompetitionSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()
    contestants = serializers.SerializerMethodField()
    class Meta:
        model = Competition
        fields = [
            "id", "name", "description", "start_date", "end_date", "starting_balance", "price_pool_cash",
            "max_daily_loss", "max_total_drawdown", "entry_fee", "prize_structure", "is_active", "contestants", "ended", "ended_at"
        ]

    def get_contestants(self, obj):
        mt5_users = MT5User.objects.filter(competition=obj)
        return mt5_users.count()

    def get_is_active(self, obj):
        now = timezone.now()
        return obj.start_date < now <= obj.end_date
    

class CompetitionResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionResult
        fields =[
            "id", "login", "rank", "username", "starting_balance", "final_equity", "profit", "return_percent",
            "max_drawdown", "total_trades", "winning_trades", "win_rate", "score"
        ]