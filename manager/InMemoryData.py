from typing import Dict, Set, List, Optional
from dataclasses import dataclass
from datetime import datetime, time, date
from decimal import Decimal

@dataclass
class AccountData:
    # mt5_user_id: Optional[int] 
    login: int

    currency_digits: int = 0

    balance: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")

    margin: Decimal = Decimal("0")
    prev_margin: Decimal = Decimal("0")
    margin_free: Decimal = Decimal("0")
    prev_margin_free: Decimal = Decimal("0")
    margin_level: Decimal = Decimal("0")
    margin_leverage: int = 0
    margin_initial: Decimal = Decimal("0")
    margin_maintenance: Decimal = Decimal("0")

    profit: Decimal = Decimal("0")
    storage: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    floating: Decimal = Decimal("0")
    equity: Decimal = Decimal("0")
    prev_equity: Decimal = Decimal("0")

    so_activation: Optional[int] = None
    so_time: Optional[int] = None  # bigint → python int
    so_level: Decimal = Decimal("0")
    so_equity: Decimal = Decimal("0")
    so_margin: Decimal = Decimal("0")

    blocked_commission: Decimal = Decimal("0")
    blocked_profit: Decimal = Decimal("0")

    assets: Decimal = Decimal("0")
    liabilities: Decimal = Decimal("0")

    active: bool = True

    step: int = 1

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None



@dataclass
class PositionData:
    # Core identifiers
    position_id: int
    login: int
    symbol: str
    comment: Optional[str] = None

    # Prices
    price_open: float = 0.0
    price_current: float = 0.0
    price_sl: float = 0.0
    price_tp: float = 0.0
    price_gateway: float = 0.0

    # Volumes
    volume: int = 0
    volume_ext: int = 0
    volume_gateway_ext: int = 0

    # Profit / financials
    profit: float = 0.0
    storage: float = 0.0
    contract_size: float = 0.0
    rate_margin: float = 0.0
    rate_profit: float = 0.0

    # Meta info
    expert_id: int = 0
    expert_position_id: int = 0
    dealer: int = 0
    external_id: Optional[str] = None

    # Timestamps
    time_create: Optional[datetime] = None
    time_update: Optional[datetime] = None

    # Status fields
    action: int = 0
    reason: int = 0
    digits: int = 0
    digits_currency: int = 0

    # Extra
    obsolete_value: float = 0.0
    activation_flags: int = 0
    activation_mode: int = 0
    activation_price: float = 0.0
    activation_time: int = 0

    closed: bool = False

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class DailyDrawdownData:
    login: int                           # MT5 account login
    date: date                           # The day of the drawdown
    equity_high: Decimal = Decimal("0")  # highest equity seen that day
    equity_low: Decimal = Decimal("0")   # lowest equity seen that day
    drawdown_percent: Decimal = Decimal("0")  # (high - low) / high * 100

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AccountTotalDrawdownData:
    login: int                                  # MT5 account login
    equity_peak: Decimal = Decimal("0")         # all-time high equity
    equity_low: Decimal = Decimal("0")          # lowest equity since peak
    drawdown_percent: Decimal = Decimal("0")    # (peak - low) / peak * 100

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None