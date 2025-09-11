from rest_framework import serializers
from .models import PropFirmChallenge, ChallengeCertificate


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