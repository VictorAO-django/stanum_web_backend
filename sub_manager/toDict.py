from datetime import datetime
from django.utils import timezone

def account_to_dict(account_obj):
    return dict(
        login=getattr(account_obj, "Login", None),
        currency_digits=getattr(account_obj, "CurrencyDigits", 0),
        balance=getattr(account_obj, "Balance", 0),
        credit=getattr(account_obj, "Credit", 0),
        margin=getattr(account_obj, "Margin", 0),
        margin_free=getattr(account_obj, "MarginFree", 0),
        margin_level=getattr(account_obj, "MarginLevel", 0),
        margin_leverage=getattr(account_obj, "MarginLeverage", 0),
        margin_initial=getattr(account_obj, "MarginInitial", 0),
        margin_maintenance=getattr(account_obj, "MarginMaintenance", 0),
        profit=getattr(account_obj, "Profit", 0),
        storage=getattr(account_obj, "Storage", 0),
        commission=getattr(account_obj, "Commission", 0),
        floating=getattr(account_obj, "Floating", 0),
        equity=getattr(account_obj, "Equity", 0),
        so_activation=getattr(account_obj, "SOActivation", None),
        so_time=getattr(account_obj, "SOTime", None),
        so_level=getattr(account_obj, "SOLevel", 0),
        so_equity=getattr(account_obj, "SOEquity", 0),
        so_margin=getattr(account_obj, "SOMargin", 0),
        blocked_commission=getattr(account_obj, "BlockedCommission", 0),
        blocked_profit=getattr(account_obj, "BlockedProfit", 0),
        assets=getattr(account_obj, "Assets", 0),
        liabilities=getattr(account_obj, "Liabilities", 0),
        updated_at=timezone.now().isoformat(),  # make JSON serializable
    )




def user_to_dict(user_obj):
    """Convert MT5 user object to a JSON-serializable dict"""

    def to_str(value):
        return str(value) if value is not None else None

    def to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def to_datetime(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()  # ✅ JSON-serializable
        try:
            return datetime.fromisoformat(str(value)).isoformat()
        except Exception:
            return None

    return dict(
        login=to_int(getattr(user_obj, "Login", 0)),
        group=to_str(getattr(user_obj, "Group", None)),
        cert_serial_number=to_int(getattr(user_obj, "CertSerialNumber", 0)),
        rights=to_int(getattr(user_obj, "Rights", 0)),

        registration=to_datetime(getattr(user_obj, "Registration", None)),
        last_access=to_datetime(getattr(user_obj, "LastAccess", None)),
        last_ip=to_str(getattr(user_obj, "LastIP", None)),

        first_name=to_str(getattr(user_obj, "FirstName", None)),
        last_name=to_str(getattr(user_obj, "LastName", None)),
        middle_name=to_str(getattr(user_obj, "MiddleName", None)),
        name=to_str(getattr(user_obj, "Name", None)),
        company=to_str(getattr(user_obj, "Company", None)),
        account=to_str(getattr(user_obj, "Account", None)),
        country=to_str(getattr(user_obj, "Country", None)),
        city=to_str(getattr(user_obj, "City", None)),
        state=to_str(getattr(user_obj, "State", None)),
        zipcode=to_str(getattr(user_obj, "ZIPCode", None)),
        address=to_str(getattr(user_obj, "Address", None)),

        phone=to_str(getattr(user_obj, "Phone", None)),
        email=to_str(getattr(user_obj, "EMail", None)),
        phone_password=to_str(getattr(user_obj, "PhonePassword", None)),

        id_document=to_str(getattr(user_obj, "ID", None)),
        mqid=to_int(getattr(user_obj, "MQID", 0)),
        client_id=to_int(getattr(user_obj, "ClientID", 0)),
        visitor_id=to_int(getattr(user_obj, "VisitorID", 0)),

        status=to_str(getattr(user_obj, "Status", None)),
        comment=to_str(getattr(user_obj, "Comment", None)),
        color=to_int(getattr(user_obj, "Color", 0)),
        last_pass_change=to_datetime(getattr(user_obj, "LastPassChange", None)),
        password_hash=to_str(getattr(user_obj, "PasswordHash", None)),
        otp_secret=to_str(getattr(user_obj, "OTPSecret", None)),
        leverage=to_int(getattr(user_obj, "Leverage", 100)),
        language=to_int(getattr(user_obj, "Language", 0)),

        lead_source=to_str(getattr(user_obj, "LeadSource", None)),
        lead_campaign=to_str(getattr(user_obj, "LeadCampaign", None)),

        interest_rate=to_float(getattr(user_obj, "InterestRate", 0.0)),
        commission_daily=to_float(getattr(user_obj, "CommissionDaily", 0.0)),
        commission_monthly=to_float(getattr(user_obj, "CommissionMonthly", 0.0)),
        commission_agent_daily=to_float(getattr(user_obj, "CommissionAgentDaily", 0.0)),
        commission_agent_monthly=to_float(getattr(user_obj, "CommissionAgentMonthly", 0.0)),
        agent=to_int(getattr(user_obj, "Agent", 0)),

        balance=to_float(getattr(user_obj, "Balance", 0.0)),
        balance_prev_day=to_float(getattr(user_obj, "BalancePrevDay", 0.0)),
        balance_prev_month=to_float(getattr(user_obj, "BalancePrevMonth", 0.0)),
        equity_prev_day=to_float(getattr(user_obj, "EquityPrevDay", 0.0)),
        equity_prev_month=to_float(getattr(user_obj, "EquityPrevMonth", 0.0)),
        credit=to_float(getattr(user_obj, "Credit", 0.0)),

        limit_orders=to_int(getattr(user_obj, "LimitOrders", 0)),
        limit_positions_value=to_float(getattr(user_obj, "LimitPositionsValue", 0.0)),
    )




def position_to_dict(pos_obj):
    """Convert MT5 position object into a JSON-safe dict"""
    from datetime import datetime, timezone

    def to_float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def to_str(value):
        return str(value) if value is not None else None

    def convert_time(epoch):
        if not epoch:
            return None
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        except Exception:
            return None
        
    def convert_time(epoch):
        try:
            return int(epoch) if epoch else 0
        except Exception:
            return 0

    return dict(
        position_id=to_int(getattr(pos_obj, "Position", 0)),
        login=to_int(getattr(pos_obj, "Login", 0)),
        symbol=to_str(getattr(pos_obj, "Symbol", None)),
        comment=to_str(getattr(pos_obj, "Comment", None)),

        price_open=to_float(getattr(pos_obj, "PriceOpen", 0.0)),
        price_current=to_float(getattr(pos_obj, "PriceCurrent", 0.0)),
        price_sl=to_float(getattr(pos_obj, "PriceSL", 0.0)),
        price_tp=to_float(getattr(pos_obj, "PriceTP", 0.0)),
        price_gateway=to_float(getattr(pos_obj, "PriceGateway", 0.0)),

        volume=to_float(getattr(pos_obj, "Volume", 0.0)),
        volume_ext=to_float(getattr(pos_obj, "VolumeExt", 0.0)),
        volume_gateway_ext=to_float(getattr(pos_obj, "VolumeGatewayExt", 0.0)),

        profit=to_float(getattr(pos_obj, "Profit", 0.0)),
        storage=to_float(getattr(pos_obj, "Storage", 0.0)),
        contract_size=to_float(getattr(pos_obj, "ContractSize", 0.0)),
        rate_margin=to_float(getattr(pos_obj, "RateMargin", 0.0)),
        rate_profit=to_float(getattr(pos_obj, "RateProfit", 0.0)),

        expert_id=to_int(getattr(pos_obj, "ExpertID", 0)),
        expert_position_id=to_int(getattr(pos_obj, "ExpertPositionID", 0)),
        dealer=to_int(getattr(pos_obj, "Dealer", 0)),
        external_id=to_str(getattr(pos_obj, "ExternalID", None)),

        time_create=convert_time(getattr(pos_obj, "TimeCreate", None)),
        time_update=convert_time(getattr(pos_obj, "TimeUpdate", None)),

        action=to_int(getattr(pos_obj, "Action", 0)),
        reason=to_int(getattr(pos_obj, "Reason", 0)),

        digits=to_int(getattr(pos_obj, "Digits", 0)),
        digits_currency=to_int(getattr(pos_obj, "DigitsCurrency", 0)),

        obsolete_value=to_float(getattr(pos_obj, "ObsoleteValue", 0.0)),

        activation_flags=to_int(getattr(pos_obj, "ActivationFlags", 0)),
        activation_mode=to_int(getattr(pos_obj, "ActivationMode", 0)),
        activation_price=to_float(getattr(pos_obj, "ActivationPrice", 0.0)),
        activation_time=convert_time(getattr(pos_obj, "ActivationTime", 0)),
    )




def deal_to_dict(deal_obj):
    """Convert MT5 deal object into JSON-safe dict"""

    def to_float(v): 
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    def to_int(v): 
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    def to_str(v): 
        return str(v) if v is not None else None

    def to_epoch(v):
        """Ensure we always return an integer epoch timestamp or None"""
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None

    return dict(
        deal=to_int(getattr(deal_obj, "Deal", 0)),
        external_id=to_str(getattr(deal_obj, "ExternalID", None)),
        login=to_int(getattr(deal_obj, "Login", 0)),
        dealer=to_int(getattr(deal_obj, "Dealer", 0)),
        order=to_int(getattr(deal_obj, "Order", 0)),
        action=to_int(getattr(deal_obj, "Action", 0)),
        entry=to_int(getattr(deal_obj, "Entry", 0)),
        digits=to_int(getattr(deal_obj, "Digits", 0)),
        digits_currency=to_int(getattr(deal_obj, "DigitsCurrency", 0)),
        contract_size=to_float(getattr(deal_obj, "ContractSize", 0)),

        time=to_epoch(getattr(deal_obj, "Time", None)),      # ✅ int, not ISO string
        time_msc=to_epoch(getattr(deal_obj, "TimeMsc", None)),

        symbol=to_str(getattr(deal_obj, "Symbol", None)),
        price=to_float(getattr(deal_obj, "Price", 0)),
        price_sl=to_float(getattr(deal_obj, "PriceSL", 0)),
        price_tp=to_float(getattr(deal_obj, "PriceTP", 0)),
        price_position=to_float(getattr(deal_obj, "PricePosition", 0)),

        volume=to_float(getattr(deal_obj, "Volume", 0)),
        volume_ext=to_float(getattr(deal_obj, "VolumeExt", 0)),
        volume_closed=to_float(getattr(deal_obj, "VolumeClosed", 0)),
        volume_closed_ext=to_float(getattr(deal_obj, "VolumeClosedExt", 0)),

        profit=to_float(getattr(deal_obj, "Profit", 0)),
        profit_raw=to_float(getattr(deal_obj, "ProfitRaw", 0)),
        value=to_float(getattr(deal_obj, "Value", 0)),
        storage=to_float(getattr(deal_obj, "Storage", 0)),
        commission=to_float(getattr(deal_obj, "Commission", 0)),
        fee=to_float(getattr(deal_obj, "Fee", 0)),

        rate_profit=to_float(getattr(deal_obj, "RateProfit", 0)),
        rate_margin=to_float(getattr(deal_obj, "RateMargin", 0)),

        expert_id=to_int(getattr(deal_obj, "ExpertID", 0)),
        position_id=to_int(getattr(deal_obj, "PositionID", 0)),

        comment=to_str(getattr(deal_obj, "Comment", None)),
        tick_value=to_float(getattr(deal_obj, "TickValue", 0)),
        tick_size=to_float(getattr(deal_obj, "TickSize", 0)),

        flags=to_int(getattr(deal_obj, "Flags", 0)),
        reason=to_int(getattr(deal_obj, "Reason", 0)),

        gateway=to_str(getattr(deal_obj, "Gateway", None)),
        price_gateway=to_float(getattr(deal_obj, "PriceGateway", 0)),
        volume_gateway_ext=to_float(getattr(deal_obj, "VolumeGatewayExt", 0)),
        action_gateway=to_int(getattr(deal_obj, "ActionGateway", 0)),

        market_bid=to_float(getattr(deal_obj, "MarketBid", 0)),
        market_ask=to_float(getattr(deal_obj, "MarketAsk", 0)),
        market_last=to_float(getattr(deal_obj, "MarketLast", 0)),

        modification_flags=to_int(getattr(deal_obj, "ModificationFlags", 0)),
    )
