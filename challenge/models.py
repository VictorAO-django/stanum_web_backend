from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model

User = get_user_model()

class PropFirmChallenge(models.Model):
    CHALLENGE_TYPES = [
        ('one_step', 'One Step'),
        ('two_step', 'Two Step'),
        ('instant', 'Funding'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('coming_soon', 'Coming Soon'),
        ('ended', 'Ended'),
    ]
    
    INSTRUMENT_CHOICES = [
        ('forex', 'Forex'),
        ('indices', 'Indices'),
        ('commodities', 'Commodities'),
        ('crypto', 'Crypto'),
        ('all', 'All Instruments'),
    ]
    
    CHALLENGE_CLASS = [
        ('challenge', 'Challenge'),
        ('challenge_funding', 'Challenge Funding'),
        ('skill_check', 'Skill check'),
        ('skill_check_funding', 'Skill Check Funding'),
    ]

    # Basic Info
    name = models.CharField(max_length=200)
    firm_name = models.CharField(max_length=100)
    description = models.TextField()
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    challenge_class = models.CharField(max_length=255, choices=CHALLENGE_CLASS, default='challenge')

    # Financial Details
    account_size = models.DecimalField(max_digits=12, decimal_places=2)
    challenge_fee = models.DecimalField(max_digits=10, decimal_places=2)
    refundable_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    profit_split_percent = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    
    # Trading Rules
    max_daily_loss_percent = models.DecimalField(max_digits=5, decimal_places=2)
    max_total_loss_percent = models.DecimalField(max_digits=5, decimal_places=2)
    additional_phase_total_loss_percent = models.DecimalField(default=8.00, max_digits=5, decimal_places=2)
    profit_target_percent = models.DecimalField(max_digits=5, decimal_places=2)
    min_trading_days = models.IntegerField()
    max_trading_days = models.IntegerField(null=True, blank=True)
    additional_trading_days = models.IntegerField(null=True, blank=True)
    
    #TwoStep Configs
    phase_2_profit_target_percent = models.DecimalField(max_digits=5, decimal_places=2)
    phase_2_min_trading_days = models.IntegerField(null=True, blank=True)
    phase_2_max_trading_days = models.IntegerField(null=True, blank=True)

    # Additional Rules
    consistency_rule_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weekend_holding = models.BooleanField(default=True)
    news_trading_allowed = models.BooleanField(default=True)
    ea_allowed = models.BooleanField(default=True)
    copy_trading_allowed = models.BooleanField(default=False)
    
    # Instruments
    allowed_instruments = models.CharField(max_length=20, choices=INSTRUMENT_CHOICES, default='all')
    
    # Meta Info
    duration_days = models.IntegerField()
    max_participants = models.IntegerField(null=True, blank=True)
    current_participants = models.IntegerField(default=0)
    
    # HFT Detection
    max_trades_per_minute = models.IntegerField(default=5)  # to detect HFT
    max_trades_per_hour = models.IntegerField(default=100)
    min_trade_duration_seconds = models.IntegerField(default=30)  # prevent scalping abuse

    # Prohibited Strategies
    grid_trading_allowed = models.BooleanField(default=False)
    martingale_allowed = models.BooleanField(default=False)
    hedging_within_account_allowed = models.BooleanField(default=True)
    cross_account_hedging_allowed = models.BooleanField(default=False)

    # Arbitrage Detection
    statistical_arbitrage_allowed = models.BooleanField(default=False)
    latency_arbitrage_allowed = models.BooleanField(default=False)
    market_making_allowed = models.BooleanField(default=False)

    # Position Rules
    max_risk_per_trade_percent = models.DecimalField(max_digits=5, decimal_places=2, default=3.00)
    max_orders_per_symbol = models.IntegerField(default=2)
    overall_risk_limit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)

    # Flexibility Rules
    stop_loss_required = models.BooleanField(default=False)
    max_inactive_days_percent = models.DecimalField(max_digits=5, decimal_places=2, default=30.00)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'propfirm_challenges'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['firm_name']),
            models.Index(fields=['status']),
            models.Index(fields=['challenge_type']),
            models.Index(fields=['account_size']),
        ]
    
    def __str__(self):
        return f"{self.firm_name} - {self.name} (${self.account_size})"
    
    @property
    def is_available(self):
        """Check if challenge is available for registration"""
        if self.status != 'active':
            return False
        if self.max_participants and self.current_participants >= self.max_participants:
            return False
        return True
    
    @property
    def spots_remaining(self):
        """Get remaining spots if max_participants is set"""
        if self.max_participants:
            return max(0, self.max_participants - self.current_participants)
        return None
    
    @classmethod
    def get_active_challenges(cls):
        """Get all active challenges"""
        return cls.objects.filter(status='active')
    
    @classmethod
    def get_by_firm(cls, firm_name):
        """Get challenges by firm name"""
        return cls.objects.filter(firm_name__icontains=firm_name)
    
    @classmethod
    def get_by_account_size_range(cls, min_size, max_size):
        """Get challenges within account size range"""
        return cls.objects.filter(account_size__gte=min_size, account_size__lte=max_size)
    
    @classmethod
    def get_affordable_challenges(cls, budget):
        """Get challenges within user's budget"""
        return cls.objects.filter(challenge_fee__lte=budget, status='active')



class ChallengeCertificate(models.Model):
    CHALLENGE_CLASS = [
        ('challenge', 'Challenge'),
        ('skill_check', 'Skill check')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    challenge_class = models.CharField(max_length=255, choices=CHALLENGE_CLASS)
    name = models.CharField(max_length=255)
    account_size = models.BigIntegerField()
    profit = models.DecimalField(max_digits=20, decimal_places=2)

    def __str__(self):
        return f"{self.user.full_name} - {self.challenge_class}"
# Create your models here.
