import MT5Manager, json, uuid
from sub_manager.InMemoryData import *
from challenge.models import PropFirmChallenge, Competition

class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj) 
        return super().default(obj)

def transform_position(pos:MT5Manager.MTPosition):
    pos_state = PositionData(
        position_id=pos.Position, login=pos.Login, symbol=pos.Symbol, comment=pos.Comment,
        price_open=pos.PriceOpen, price_current=pos.PriceCurrent, price_sl=pos.PriceSL,
        price_tp=pos.PriceTP, price_gateway=pos.PriceGateway, volume=pos.Volume, volume_ext=pos.VolumeExt,
        volume_gateway_ext=pos.VolumeGatewayExt, profit=pos.Profit, storage=pos.Storage, contract_size=pos.ContractSize,
        rate_margin=pos.RateMargin, rate_profit=pos.RateProfit, expert_id=pos.ExpertID, expert_position_id=pos.ExpertPositionID,
        dealer=pos.Dealer, external_id=pos.ExternalID, time_create=pos.TimeCreate, time_update=pos.TimeUpdate,
        action=pos.Action, reason=pos.Reason, digits=pos.Digits, digits_currency=pos.DigitsCurrency, obsolete_value=pos.ObsoleteValue
    )
    return pos_state

def transform_deal(deal:MT5Manager.MTDeal):
    deal_state = DealData(
        deal=deal.Deal, login=deal.Login, order=deal.Order, external_id=deal.ExternalID, dealer=deal.Dealer,
        action=deal.Action, entry=deal.Entry, symbol=deal.Symbol, comment=deal.Comment, reason=deal.Reason,
        action_gateway=deal.ActionGateway, gateway=deal.Gateway, price=float(deal.Price), price_sl=float(deal.PriceSL),
        price_tp=float(deal.PriceTP), price_position=float(deal.PricePosition), price_gateway=float(deal.PriceGateway),
        market_bid=float(deal.MarketBid), market_ask=float(deal.MarketAsk), market_last=float(deal.MarketLast),
        volume=deal.Volume, volume_ext=float(deal.VolumeExt), volume_closed=deal.VolumeClosed, volume_closed_ext=float(deal.VolumeClosedExt),
        volume_gateway_ext=float(deal.VolumeGatewayExt), profit=float(deal.Profit), profit_raw=float(deal.ProfitRaw),
        value=float(deal.Value), storage=float(deal.Storage), commission=float(deal.Commission), fee=float(deal.Fee),
        contract_size=float(deal.ContractSize), tick_value=float(deal.TickValue), tick_size=float(deal.TickValue),
        rate_profit=float(deal.RateProfit), rate_margin=float(deal.RateMargin), digits=deal.Digits, digits_currency=deal.DigitsCurrency,
        expert_id=deal.ExpertID, position_id=deal.PositionID, flags=deal.Flags, modification_flags=deal.ModificationFlags,
        time=deal.Time, time_msc=deal.TimeMsc,
    )
    return deal_state

def transform_account(acc:MT5Manager.MTAccount):
    data = AccountData(
        login=acc.Login, currency_digits=acc.CurrencyDigits, balance=acc.Balance, credit=acc.Credit, margin=acc.Margin,
        margin_free=acc.MarginFree, margin_level=acc.MarginLeverage,
        margin_leverage=acc.MarginLeverage, margin_initial=acc.MarginInitial, margin_maintenance=acc.MarginMaintenance,
        profit=acc.Profit, storage=acc.Storage, floating=acc.Floating, equity=acc.Equity,
        so_activation=acc.SOActivation, so_time=acc.SOTime, so_level=acc.SOLevel, so_equity=acc.SOEquity, so_margin=acc.SOMargin,
        blocked_commission=acc.BlockedCommission, blocked_profit=acc.BlockedProfit, assets=acc.Assets, liabilities=acc.Liabilities,
        #created_at=None, updated_at=acc.updated_at, step=acc.step, active=True, prev_equity=acc.prev_equity,
    )
    return data

def transform_tick(symbol, tick:MT5Manager.MTTickShort):
    data = TickData(
        symbol=symbol, datetime=tick.datetime, bid=tick.bid, ask=tick.ask,
        last=tick.last, volume=tick.volume, datetime_msc=tick.datetime_msc, volume_ext=tick.volume_ext
    )
    return data

def transform_propfirmchallenge(ch:PropFirmChallenge):
    data = PropFirmChallengeData(
        name=ch.name, firm_name=ch.firm_name, description=ch.description, challenge_type=ch.challenge_type,
        account_size=ch.account_size, challenge_fee=ch.challenge_fee, status=ch.status, challenge_class=ch.challenge_class,
        refundable_fee=ch.refundable_fee, profit_split_percent=ch.profit_split_percent, max_daily_loss_percent=ch.max_daily_loss_percent,
        max_total_loss_percent=ch.max_total_loss_percent, additional_phase_total_loss_percent=ch.additional_phase_total_loss_percent,
        profit_target_percent=ch.profit_target_percent, min_trading_days=ch.min_trading_days, max_trading_days=ch.max_trading_days,
        additional_trading_days=ch.additional_trading_days, phase_2_profit_target_percent=ch.phase_2_profit_target_percent, 
        phase_2_min_trading_days=ch.phase_2_min_trading_days, phase_2_max_trading_days=ch.phase_2_max_trading_days, consistency_rule_percent=ch.consistency_rule_percent,
        weekend_holding=ch.weekend_holding, news_trading_allowed=ch.news_trading_allowed, ea_allowed=ch.ea_allowed, copy_trading_allowed=ch.copy_trading_allowed,
        allowed_instruments=ch.allowed_instruments, duration_days=ch.duration_days, max_participants=ch.max_participants,
        current_participants=ch.current_participants, max_trades_per_minute=ch.max_trades_per_minute, max_trades_per_hour=ch.max_trades_per_hour,
        min_trade_duration_seconds=ch.min_trade_duration_seconds, grid_trading_allowed=ch.grid_trading_allowed,
        martingale_allowed=ch.martingale_allowed, hedging_within_account_allowed=ch.hedging_within_account_allowed,
        cross_account_hedging_allowed=ch.cross_account_hedging_allowed, statistical_arbitrage_allowed=ch.statistical_arbitrage_allowed,
        latency_arbitrage_allowed=ch.latency_arbitrage_allowed, market_making_allowed=ch.market_making_allowed, 
        max_risk_per_trade_percent=ch.max_risk_per_trade_percent, max_orders_per_symbol=ch.max_orders_per_symbol, overall_risk_limit_percent=ch.overall_risk_limit_percent,
        stop_loss_required=ch.stop_loss_required, max_inactive_days_percent=ch.max_inactive_days_percent, created_at=ch.created_at,
        updated_at=ch.updated_at
    )
    return data


def transform_competition(competition:Competition):
    """Build CompetitionData from a Competition Django model instance"""
    return CompetitionData(
        uuid=competition.uuid,
        name=competition.name,
        description=competition.description,
        start_date=competition.start_date,
        end_date=competition.end_date,
        starting_balance=competition.starting_balance,
        max_daily_loss=competition.max_daily_loss,
        max_total_drawdown=competition.max_total_drawdown,
        entry_fee=competition.entry_fee,
        price_pool_cash=competition.price_pool_cash,
        prize_structure=getattr(competition, "prize_structure", {}) or {}
    )