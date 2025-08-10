# models.py
from django.db import models
from django.utils import timezone
from decimal import Decimal
import json
from django.contrib.auth import get_user_model
from challenge.models import PropFirmChallenge

User = get_user_model()

class TradingAccount(models.Model):
    ACCOUNT_TYPES = (
        ('challenge', 'Challenge Account'),
        ('funded', 'Funded Account'),
        ('live', 'Live Account'),
    )
    
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('disabled', 'Disabled'),
        ('challenge_passed', 'Challenge Passed'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
    )
    
    # Basic account info
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trading_accounts')
    challenge = models.ForeignKey(PropFirmChallenge, null=True, on_delete=models.CASCADE)

    metaapi_account_id = models.CharField(max_length=100, unique=True, db_index=True)
    login = models.CharField(max_length=50)
    password = models.CharField(max_length=100)  # Consider encrypting this
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    size = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Account settings
    server = models.CharField(max_length=100, default="MetaQuotes-Demo")
    leverage = models.IntegerField(default=100)
    
    # Financial data
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    equity = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    margin = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    free_margin = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    margin_level = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Risk management settings
    risk_daily_loss_limit = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.05'))  # 5%
    risk_max_drawdown = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.10'))  # 10%
    risk_profit_target = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.08'))  # 8%
    max_daily_trades = models.IntegerField(default=50)
    
    # Status tracking
    disable_reason = models.TextField(blank=True, null=True)
    disabled_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    
    selected_date = models.DateTimeField(default=timezone.now, null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trading_accounts'
        ordering = ['-created_at', '-selected_date']
        indexes = [
            models.Index(fields=['user', 'account_type']),
            models.Index(fields=['status']),
            models.Index(fields=['metaapi_account_id']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.account_type} ({self.metaapi_account_id})"
    
    @property
    def is_active(self):
        return self.status == 'active'
    
    @property
    def daily_loss_limit_amount(self):
        return self.balance * self.risk_daily_loss_limit
    
    @property
    def max_drawdown_amount(self):
        return self.balance * self.risk_max_drawdown


class Trade(models.Model):
    TYPE_CHOICES = (
        ('buy', 'Buy'),
        ('sell', 'Sell'),
    )
    
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('cancelled', 'Cancelled'),
    )
    
    # Relationships
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='trades')
    
    # Trade identification
    position_id = models.CharField(max_length=100, db_index=True)
    order_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Trade details
    symbol = models.CharField(max_length=20)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    volume = models.DecimalField(max_digits=10, decimal_places=5)
    
    # Pricing
    open_price = models.DecimalField(max_digits=15, decimal_places=5)
    current_price = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True)
    close_price = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True)
    
    # Stop Loss / Take Profit
    stop_loss = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True)
    take_profit = models.DecimalField(max_digits=15, decimal_places=5, blank=True, null=True)
    
    # Financial results
    profit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    swap = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    commission = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Status and timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    open_time = models.DateTimeField()
    close_time = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trades'
        ordering = ['-open_time']
        indexes = [
            models.Index(fields=['account', 'status']),
            models.Index(fields=['symbol', 'open_time']),
            models.Index(fields=['position_id']),
        ]
        unique_together = ['account', 'position_id']
    
    def __str__(self):
        return f"{self.account.user.username} - {self.type.upper()} {self.volume} {self.symbol}"
    
    @property
    def total_result(self):
        return self.profit + self.swap + self.commission
    
    @property
    def duration(self):
        if self.close_time:
            return self.close_time - self.open_time
        return timezone.now() - self.open_time


class AccountActivity(models.Model):
    ACTIVITY_TYPES = (
        ('account_created', 'Account Created'),
        ('account_disabled', 'Account Disabled'),
        ('challenge_passed', 'Challenge Passed'),
        ('position_opened', 'Position Opened'),
        ('position_closed', 'Position Closed'),
        ('deal_executed', 'Deal Executed'),
        ('balance_update', 'Balance Update'),
        ('risk_violation', 'Risk Violation'),
        ('account_promoted', 'Account Promoted'),
    )
    
    # Relationships
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='activities')
    related_trade = models.ForeignKey(Trade, on_delete=models.SET_NULL, blank=True, null=True)
    
    # Activity details
    activity_type = models.CharField(max_length=30, choices=ACTIVITY_TYPES)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # Additional data (JSON field for flexible storage)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'account_activities'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['account', 'activity_type']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.account.user.username} - {self.activity_type} at {self.timestamp}"


class DailyAccountStats(models.Model):
    """Track daily statistics for each account"""
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='daily_stats')
    date = models.DateField()
    
    # Starting values
    starting_balance = models.DecimalField(max_digits=15, decimal_places=2)
    starting_equity = models.DecimalField(max_digits=15, decimal_places=2)
    
    # Daily tracking
    highest_equity = models.DecimalField(max_digits=15, decimal_places=2)
    lowest_equity = models.DecimalField(max_digits=15, decimal_places=2)
    ending_equity = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # Trade statistics
    trades_count = models.IntegerField(default=0)
    winning_trades = models.IntegerField(default=0)
    losing_trades = models.IntegerField(default=0)
    
    # P&L tracking
    daily_pnl = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gross_profit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    gross_loss = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Risk metrics
    max_drawdown_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0.0000'))
    daily_loss_pct = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0.0000'))
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'daily_account_stats'
        ordering = ['-date']
        unique_together = ['account', 'date']
        indexes = [
            models.Index(fields=['account', 'date']),
            models.Index(fields=['date']),
        ]
    
    def __str__(self):
        return f"{self.account.user.username} - {self.date} (P&L: {self.daily_pnl})"
    
    @property
    def win_rate(self):
        if self.trades_count == 0:
            return 0
        return (self.winning_trades / self.trades_count) * 100
    
    @property
    def profit_factor(self):
        if self.gross_loss == 0:
            return float('inf') if self.gross_profit > 0 else 0
        return abs(self.gross_profit / self.gross_loss)


class UserProfile(models.Model):
    """Extended user profile for prop firm"""
    TIER_CHOICES = (
        ('basic', 'Basic'),
        ('pro', 'Professional'),
        ('elite', 'Elite'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='trading_profile')
    
    # Personal info
    phone_number = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Trading experience
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='basic')
    years_experience = models.IntegerField(default=0)
    
    # Account limits
    max_challenge_accounts = models.IntegerField(default=3)
    max_funded_accounts = models.IntegerField(default=1)
    
    # Subscription and billing
    subscription_active = models.BooleanField(default=False)
    subscription_expires = models.DateTimeField(blank=True, null=True)
    
    # Statistics
    total_challenges_attempted = models.IntegerField(default=0)
    challenges_passed = models.IntegerField(default=0)
    total_profit_earned = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'user_profiles'
    
    def __str__(self):
        return f"{self.user.username} - {self.tier.title()} Tier"
    
    @property
    def challenge_pass_rate(self):
        if self.total_challenges_attempted == 0:
            return 0
        return (self.challenges_passed / self.total_challenges_attempted) * 100
    
    def can_create_challenge_account(self):
        active_challenges = self.user.trading_accounts.filter(
            account_type='challenge',
            status='active'
        ).count()
        return active_challenges < self.max_challenge_accounts
    
    def can_create_funded_account(self):
        active_funded = self.user.trading_accounts.filter(
            account_type='funded',
            status='active'
        ).count()
        return active_funded < self.max_funded_accounts