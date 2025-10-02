from typing import Dict, Set, List, Optional, TypedDict, Tuple
from dataclasses import dataclass, field
import uuid as uuid_lib
from datetime import datetime, time, date, timezone
from decimal import Decimal
import MT5Manager
class ViolationDict(TypedDict):
    type: str
    message: str


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
class DealData:
    # Core identifiers
    deal: int
    login: int
    order: Optional[int] = None
    external_id: Optional[str] = None
    dealer: Optional[int] = None

    # Deal details
    action: Optional[str] = None      # Buy/Sell/etc
    entry: Optional[str] = None       # Entry direction
    symbol: Optional[str] = None
    comment: Optional[str] = None
    reason: Optional[str] = None
    action_gateway: Optional[str] = None
    gateway: Optional[str] = None

    # Prices
    price: float = 0.0
    price_sl: float = 0.0
    price_tp: float = 0.0
    price_position: float = 0.0
    price_gateway: float = 0.0
    market_bid: float = 0.0
    market_ask: float = 0.0
    market_last: float = 0.0

    # Volumes
    volume: int = 0
    volume_ext: float = 0.0
    volume_closed: int = 0
    volume_closed_ext: float = 0.0
    volume_gateway_ext: float = 0.0

    # Profit & financials
    profit: float = 0.0
    profit_raw: float = 0.0
    value: float = 0.0
    storage: float = 0.0
    commission: float = 0.0
    fee: float = 0.0
    contract_size: float = 0.0
    tick_value: float = 0.0
    tick_size: float = 0.0
    rate_profit: float = 0.0
    rate_margin: float = 0.0

    # Meta
    digits: int = 0
    digits_currency: int = 0
    expert_id: Optional[int] = None
    position_id: Optional[int] = None

    # Flags
    flags: int = 0
    modification_flags: int = 0
    deleted: bool = False

    # Timestamps
    time: Optional[int] = None        # Unix timestamp
    time_msc: Optional[int] = None    # Unix timestamp (ms)
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

@dataclass
class AccountWatermarksData:
    login: int
    hwm_balance: Decimal = Decimal("0")
    lwm_balance: Decimal = Decimal("0")
    hwm_equity: Decimal = Decimal("0")
    lwm_equity: Decimal = Decimal("0")


@dataclass
class PropFirmChallengeData:
    # Basic Info
    name: str
    firm_name: str
    description: str
    challenge_type: str
    account_size: float
    challenge_fee: float

    status: str = "active"
    challenge_class: str = "challenge"

    # Financial Details
    refundable_fee: float = 0.0
    profit_split_percent: int = 0

    # Trading Rules
    max_daily_loss_percent: float = 0.0
    max_total_loss_percent: float = 0.0
    additional_phase_total_loss_percent: float = 8.0
    profit_target_percent: float = 0.0
    min_trading_days: int = 0
    max_trading_days: Optional[int] = None
    additional_trading_days: Optional[int] = None

    # TwoStep Configs
    phase_2_profit_target_percent: float = 0.0
    phase_2_min_trading_days: Optional[int] = None
    phase_2_max_trading_days: Optional[int] = None

    # Additional Rules
    consistency_rule_percent: Optional[float] = None
    weekend_holding: bool = True
    news_trading_allowed: bool = True
    ea_allowed: bool = True
    copy_trading_allowed: bool = False

    # Instruments
    allowed_instruments: str = "all"

    # Meta Info
    duration_days: int = 0
    max_participants: Optional[int] = None
    current_participants: int = 0

    # HFT Detection
    max_trades_per_minute: int = 5
    max_trades_per_hour: int = 100
    min_trade_duration_seconds: int = 30

    # Prohibited Strategies
    grid_trading_allowed: bool = False
    martingale_allowed: bool = False
    hedging_within_account_allowed: bool = True
    cross_account_hedging_allowed: bool = False

    # Arbitrage Detection
    statistical_arbitrage_allowed: bool = False
    latency_arbitrage_allowed: bool = False
    market_making_allowed: bool = False

    # Position Rules
    max_risk_per_trade_percent: float = 3.0
    max_orders_per_symbol: int = 2
    overall_risk_limit_percent: float = 10.0

    # Flexibility Rules
    stop_loss_required: bool = False
    max_inactive_days_percent: float = 30.0

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class TickData:
    symbol: str      
    datetime: int                 
    bid: float                    
    ask: float                      
    last: float                 
    volume: int                     
    datetime_msc: int          
    volume_ext: int       


@dataclass
class CompetitionData:
    """
    A data transfer object for Competition model.
    (Ignores daily_loss / total_loss calculations)
    """
    uuid: uuid_lib.UUID = field(default_factory=uuid_lib.uuid4)
    name: str = ""
    description: Optional[str] = None
    start_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    starting_balance: Decimal = Decimal("50000.00")
    max_daily_loss: Decimal = Decimal("0.00")
    max_total_drawdown: Decimal = Decimal("0.00")

    entry_fee: Optional[Decimal] = None
    price_pool_cash: Decimal = Decimal("5000.00")
    prize_structure: Dict[str, Decimal] = field(default_factory=dict)


    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            uuid=uuid_lib.UUID(data["uuid"]),
            name=data["name"],
            description=data.get("description"),
            start_date=datetime.fromisoformat(data["start_date"]),
            end_date=datetime.fromisoformat(data["end_date"]),
            starting_balance=Decimal(str(data["starting_balance"])),
            max_daily_loss=Decimal(str(data["max_daily_loss"])),
            max_total_drawdown=Decimal(str(data["max_total_drawdown"])),
            entry_fee=Decimal(str(data["entry_fee"])) if data.get("entry_fee") else None,
            price_pool_cash=Decimal(str(data["price_pool_cash"])),
            prize_structure={k: Decimal(str(v)) for k, v in data.get("prize_structure", {}).items()},
        )