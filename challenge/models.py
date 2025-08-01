from django.db import models

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class PropFirmChallenge(models.Model):
    CHALLENGE_TYPES = [
        ('one_step', 'One Step'),
        ('two_step', 'Two Step'),
        ('instant', 'Instant Funding'),
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
    
    # Basic Info
    name = models.CharField(max_length=200)
    firm_name = models.CharField(max_length=100)
    description = models.TextField()
    challenge_type = models.CharField(max_length=20, choices=CHALLENGE_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Financial Details
    account_size = models.DecimalField(max_digits=12, decimal_places=2)
    challenge_fee = models.DecimalField(max_digits=10, decimal_places=2)
    refundable_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    profit_split_percent = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    
    # Trading Rules
    max_daily_loss_percent = models.DecimalField(max_digits=5, decimal_places=2)
    max_total_loss_percent = models.DecimalField(max_digits=5, decimal_places=2)
    profit_target_percent = models.DecimalField(max_digits=5, decimal_places=2)
    min_trading_days = models.IntegerField()
    max_trading_days = models.IntegerField(null=True, blank=True)
    
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



class ChallengeInstrument(models.Model):
    challenge = models.ForeignKey(PropFirmChallenge, on_delete=models.CASCADE, related_name='instruments')
    instrument = models.CharField(max_length=20, choices=PropFirmChallenge.INSTRUMENT_CHOICES)
    
    class Meta:
        unique_together = ['challenge', 'instrument']
# Create your models here.
