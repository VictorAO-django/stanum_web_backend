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
    


















class MT5User(models.Model):
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
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    challenge = models.ForeignKey(PropFirmChallenge, null=True, on_delete=models.CASCADE)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES, default='challenge')
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    password = models.CharField(max_length=255, null=True)
    fail_reason = models.TextField(blank=True)
    
    # Core identifiers
    login = models.BigIntegerField(primary_key=True)  # MT5 account login
    group = models.CharField(max_length=64, blank=True, null=True)
    server = models.CharField(max_length=255, default="CommoT-Live")
    cert_serial_number = models.BigIntegerField(default=0)
    rights = models.BigIntegerField(default=0)

    # Registration & access
    registration = models.DateTimeField(blank=True, null=True)
    last_access = models.DateTimeField(blank=True, null=True)
    last_ip = models.GenericIPAddressField(blank=True, null=True)

    # Personal details
    first_name = models.CharField(max_length=64, blank=True, null=True)
    last_name = models.CharField(max_length=64, blank=True, null=True)
    middle_name = models.CharField(max_length=64, blank=True, null=True)
    name = models.CharField(max_length=128, blank=True, null=True)  # deprecated in API, but keeping
    company = models.CharField(max_length=128, blank=True, null=True)
    account = models.CharField(max_length=64, blank=True, null=True)
    country = models.CharField(max_length=64, blank=True, null=True)
    city = models.CharField(max_length=64, blank=True, null=True)
    state = models.CharField(max_length=64, blank=True, null=True)
    zipcode = models.CharField(max_length=32, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    # Contact
    phone = models.CharField(max_length=64, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone_password = models.CharField(max_length=64, blank=True, null=True)

    # Identification
    id_document = models.CharField(max_length=64, blank=True, null=True)
    mqid = models.BigIntegerField(default=0)
    client_id = models.BigIntegerField(default=0)
    visitor_id = models.BigIntegerField(default=0)

    # Account settings
    status = models.CharField(max_length=64, blank=True, null=True)
    comment = models.TextField(blank=True, null=True)
    color = models.BigIntegerField(default=0)
    last_pass_change = models.DateTimeField(blank=True, null=True)
    password_hash = models.CharField(max_length=128, blank=True, null=True)
    otp_secret = models.CharField(max_length=128, blank=True, null=True)
    leverage = models.IntegerField(default=100)
    language = models.IntegerField(default=0)

    # Lead & marketing
    lead_source = models.CharField(max_length=128, blank=True, null=True)
    lead_campaign = models.CharField(max_length=128, blank=True, null=True)

    # Financials
    interest_rate = models.FloatField(default=0.0)
    commission_daily = models.FloatField(default=0.0)
    commission_monthly = models.FloatField(default=0.0)
    commission_agent_daily = models.FloatField(default=0.0)
    commission_agent_monthly = models.FloatField(default=0.0)
    agent = models.BigIntegerField(default=0)

    balance = models.FloatField(default=0.0)
    balance_prev_day = models.FloatField(default=0.0)
    balance_prev_month = models.FloatField(default=0.0)
    equity_prev_day = models.FloatField(default=0.0)
    equity_prev_month = models.FloatField(default=0.0)
    credit = models.FloatField(default=0.0)

    # Limits
    limit_orders = models.IntegerField(default=0)
    limit_positions_value = models.FloatField(default=0.0)

    selected_date = models.DateTimeField(default=timezone.now, null=True, blank=True)

    # Meta
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mt5_users"
        verbose_name = "MT5 User"
        verbose_name_plural = "MT5 Users"

    def __str__(self):
        return f"{self.login} - {self.first_name} {self.last_name}".strip()


class MT5Account(models.Model):

    login = models.BigIntegerField(unique=True, db_index=True)

    currency_digits = models.IntegerField(default=0)

    balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    margin = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_free = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    margin_leverage = models.IntegerField(default=0)
    margin_initial = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_maintenance = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    storage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    commission = models.DecimalField(max_digits=20, decimal_places=2, default=0)  # deprecated but kept
    floating = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    equity = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    so_activation = models.IntegerField(default=0, null=True, blank=True)
    so_time = models.BigIntegerField(null=True, blank=True)
    so_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    so_equity = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    so_margin = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    blocked_commission = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    blocked_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    assets = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    liabilities = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Account {self.login} - Equity {self.equity}"


class MT5UserLoginHistory(models.Model):
    ACTION_CHOICES = (
        ('login', 'Login'),
        ('logout', 'Logout')
    )
    mt_user = models.ForeignKey(MT5User, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    ip = models.CharField(max_length=255, blank=True, null=True)
    type = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.mt_user.login} - {self.type}"


class MT5Position(models.Model):
    # Core identifiers
    position_id = models.BigIntegerField(unique=True, db_index=True)   # Position
    login = models.BigIntegerField()                                  # Login (account)
    symbol = models.CharField(max_length=50)                          # Symbol e.g. USDJPY.p
    comment = models.TextField(blank=True, null=True)

    # Prices
    price_open = models.DecimalField(max_digits=15, decimal_places=5, default=0.0)
    price_current = models.DecimalField(max_digits=15, decimal_places=5, default=0.0)
    price_sl = models.DecimalField(max_digits=15, decimal_places=5, default=0.0)
    price_tp = models.DecimalField(max_digits=15, decimal_places=5, default=0.0)
    price_gateway = models.DecimalField(max_digits=15, decimal_places=5, default=0.0)

    # Volumes
    volume = models.BigIntegerField(default=0)                         # usually in lots * 100
    volume_ext = models.BigIntegerField(default=0)
    volume_gateway_ext = models.BigIntegerField(default=0)

    # Profit / financials
    profit = models.DecimalField(max_digits=20, decimal_places=5, default=0.0)
    storage = models.DecimalField(max_digits=20, decimal_places=5, default=0.0)
    contract_size = models.DecimalField(max_digits=20, decimal_places=5, default=0.0)
    rate_margin = models.DecimalField(max_digits=20, decimal_places=10, default=0.0)
    rate_profit = models.DecimalField(max_digits=20, decimal_places=10, default=0.0)

    # Meta info
    expert_id = models.BigIntegerField(default=0)
    expert_position_id = models.BigIntegerField(default=0)
    dealer = models.BigIntegerField(default=0)
    external_id = models.CharField(max_length=255, blank=True, null=True)

    # Timestamps (converted from epoch)
    time_create = models.DateTimeField()
    time_update = models.DateTimeField()

    # Status fields
    action = models.IntegerField(default=0)
    reason = models.IntegerField(default=0)
    digits = models.IntegerField(default=0)
    digits_currency = models.IntegerField(default=0)

    # Extra
    obsolete_value = models.DecimalField(max_digits=20, decimal_places=5, default=0.0)
    activation_flags = models.IntegerField(default=0)
    activation_mode = models.IntegerField(default=0)
    activation_price = models.DecimalField(max_digits=20, decimal_places=5, default=0.0)
    activation_time = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "positions"
        indexes = [
            models.Index(fields=["login"]),
            models.Index(fields=["symbol"]),
        ]

    def __str__(self):
        return f"{self.symbol} - {self.position_id} (Login {self.login})"




class MT5Deal(models.Model):
    deal = models.BigIntegerField(unique=True, db_index=True)  # Ticket
    external_id = models.CharField(max_length=100, blank=True, null=True)
    login = models.IntegerField(db_index=True)  # Client login
    dealer = models.IntegerField(null=True, blank=True)  # Dealer login
    order = models.BigIntegerField(null=True, blank=True)

    action = models.CharField(max_length=50, blank=True, null=True)  # Buy/Sell/etc
    entry = models.CharField(max_length=50, blank=True, null=True)   # Entry direction

    digits = models.IntegerField(default=0)
    digits_currency = models.IntegerField(default=0)
    contract_size = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    time = models.BigIntegerField(null=True, blank=True)     # Unix timestamp
    time_msc = models.BigIntegerField(null=True, blank=True) # Unix timestamp (ms)
    symbol = models.CharField(max_length=50, blank=True, null=True)

    price = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_sl = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_tp = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_position = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    volume = models.BigIntegerField(default=0)
    volume_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    volume_closed = models.BigIntegerField(default=0)
    volume_closed_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_raw = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    value = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    storage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    commission = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    fee = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    rate_profit = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    rate_margin = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    expert_id = models.IntegerField(null=True, blank=True)
    position_id = models.BigIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True, null=True)

    tick_value = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    tick_size = models.DecimalField(max_digits=20, decimal_places=6, default=0)

    flags = models.BigIntegerField(default=0)
    reason = models.CharField(max_length=100, blank=True, null=True)

    gateway = models.IntegerField(null=True, blank=True)
    price_gateway = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    volume_gateway_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    action_gateway = models.CharField(max_length=50, blank=True, null=True)

    market_bid = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    market_ask = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    market_last = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    modification_flags = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Deal {self.deal} - {self.symbol} ({self.login})"


class MT5Order(models.Model):
    order = models.BigIntegerField(unique=True, db_index=True)  # Ticket
    external_id = models.CharField(max_length=100, blank=True, null=True)
    login = models.IntegerField(db_index=True)   # Client login
    dealer = models.IntegerField(null=True, blank=True)  # Dealer login
    symbol = models.CharField(max_length=50, blank=True, null=True)

    digits = models.IntegerField(default=0)
    digits_currency = models.IntegerField(default=0)
    contract_size = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    state = models.CharField(max_length=50, blank=True, null=True)
    reason = models.CharField(max_length=100, blank=True, null=True)

    time_setup = models.BigIntegerField(null=True, blank=True)
    time_setup_msc = models.BigIntegerField(null=True, blank=True)
    time_expiration = models.BigIntegerField(null=True, blank=True)
    time_done = models.BigIntegerField(null=True, blank=True)
    time_done_msc = models.BigIntegerField(null=True, blank=True)

    type = models.CharField(max_length=50, blank=True, null=True)
    type_fill = models.CharField(max_length=50, blank=True, null=True)
    type_time = models.CharField(max_length=50, blank=True, null=True)

    price_order = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_trigger = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_current = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_sl = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_tp = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    volume_initial = models.BigIntegerField(default=0)
    volume_initial_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    volume_current = models.BigIntegerField(default=0)
    volume_current_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    expert_id = models.IntegerField(null=True, blank=True)
    position_id = models.BigIntegerField(null=True, blank=True)
    position_by_id = models.BigIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True, null=True)

    activation_mode = models.CharField(max_length=50, blank=True, null=True)
    activation_time = models.BigIntegerField(null=True, blank=True)
    activation_price = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    activation_flags = models.BigIntegerField(default=0)

    rate_margin = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    modification_flags = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order} - {self.symbol} ({self.login})"
    


class MT5OrderHistory(models.Model):
    order = models.BigIntegerField(unique=True, db_index=True)  # Ticket
    external_id = models.CharField(max_length=100, blank=True, null=True)
    login = models.IntegerField(db_index=True)   # Client login
    dealer = models.IntegerField(null=True, blank=True)  # Dealer login
    symbol = models.CharField(max_length=50, blank=True, null=True)

    digits = models.IntegerField(default=0)
    digits_currency = models.IntegerField(default=0)
    contract_size = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    state = models.CharField(max_length=50, blank=True, null=True)
    reason = models.CharField(max_length=100, blank=True, null=True)

    time_setup = models.BigIntegerField(null=True, blank=True)
    time_setup_msc = models.BigIntegerField(null=True, blank=True)
    time_expiration = models.BigIntegerField(null=True, blank=True)
    time_done = models.BigIntegerField(null=True, blank=True)
    time_done_msc = models.BigIntegerField(null=True, blank=True)

    type = models.CharField(max_length=50, blank=True, null=True)
    type_fill = models.CharField(max_length=50, blank=True, null=True)
    type_time = models.CharField(max_length=50, blank=True, null=True)

    price_order = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_trigger = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_current = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_sl = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_tp = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    volume_initial = models.BigIntegerField(default=0)
    volume_initial_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)
    volume_current = models.BigIntegerField(default=0)
    volume_current_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    expert_id = models.IntegerField(null=True, blank=True)
    position_id = models.BigIntegerField(null=True, blank=True)
    position_by_id = models.BigIntegerField(null=True, blank=True)
    comment = models.TextField(blank=True, null=True)

    activation_mode = models.CharField(max_length=50, blank=True, null=True)
    activation_time = models.BigIntegerField(null=True, blank=True)
    activation_price = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    activation_flags = models.BigIntegerField(default=0)

    rate_margin = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    modification_flags = models.BigIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order} - {self.symbol} ({self.login})"
    


class MT5Summary(models.Model):
    symbol = models.CharField(max_length=64, db_index=True)
    digits = models.IntegerField(default=0)

    position_clients = models.IntegerField(default=0)
    position_coverage = models.IntegerField(default=0)

    volume_buy_clients = models.BigIntegerField(default=0)
    volume_buy_clients_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    volume_buy_coverage = models.BigIntegerField(default=0)
    volume_buy_coverage_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    volume_sell_clients = models.BigIntegerField(default=0)
    volume_sell_clients_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    volume_sell_coverage = models.BigIntegerField(default=0)
    volume_sell_coverage_ext = models.DecimalField(max_digits=30, decimal_places=10, default=0)

    volume_net = models.BigIntegerField(default=0)

    price_buy_clients = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_buy_coverage = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_sell_clients = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    price_sell_coverage = models.DecimalField(max_digits=20, decimal_places=5, default=0)

    profit_clients = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_coverage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_full_clients = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_full_coverage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_uncovered = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_uncovered_full = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("symbol",)

    def __str__(self):
        return f"Summary {self.symbol} (Net Vol: {self.volume_net})"
    


class MT5Daily(models.Model):
    datetime = models.DateTimeField(null=True, blank=True)
    datetime_prev = models.DateTimeField(null=True, blank=True)
    login = models.BigIntegerField()
    name = models.CharField(max_length=255, blank=True, null=True)
    group = models.CharField(max_length=100, blank=True, null=True)
    currency = models.CharField(max_length=20, blank=True, null=True)
    currency_digits = models.IntegerField(default=2)
    company = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    interest_rate = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    commission_daily = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    commission_monthly = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    agent_daily = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    agent_monthly = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    balance_prev_day = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    balance_prev_month = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    equity_prev_day = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    equity_prev_month = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    margin = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_free = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    margin_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    margin_leverage = models.BigIntegerField(default=1)

    profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_storage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_commission = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_equity = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_assets = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    profit_liabilities = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    daily_profit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_credit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_charge = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_correction = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_bonus = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_storage = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_comm_instant = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_comm_round = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_comm_fee = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_dividend = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_taxes = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_so_compensation = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_so_compensation_credit = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_agent = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    daily_interest = models.DecimalField(max_digits=20, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("login", "datetime")

    def __str__(self):
        return f"Daily Report - {self.login} - {self.datetime}"