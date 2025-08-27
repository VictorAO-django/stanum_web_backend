import MT5Manager
from trading.models import MT5Daily

def safe_get(obj, attr, default=None):
    """Safely get attribute or call method if callable."""
    val = getattr(obj, attr, default)
    if callable(val):
        try:
            return val()
        except Exception:
            return default
    return val

def save_mt5_daily(daily_obj: MT5Manager.MTDaily):
    daily, _ = MT5Daily.objects.update_or_create(
        login=safe_get(daily_obj, "Login"),
        datetime=safe_get(daily_obj, "Datetime"),
        defaults=dict(
            datetime_prev=safe_get(daily_obj, "DatetimePrev"),
            name=safe_get(daily_obj, "Name"),
            group=safe_get(daily_obj, "Group"),
            currency=safe_get(daily_obj, "Currency"),
            currency_digits=safe_get(daily_obj, "CurrencyDigits", 2),
            company=safe_get(daily_obj, "Company"),
            email=safe_get(daily_obj, "EMail"),
            balance=safe_get(daily_obj, "Balance", 0),
            credit=safe_get(daily_obj, "Credit", 0),
            interest_rate=safe_get(daily_obj, "InterestRate", 0),
            commission_daily=safe_get(daily_obj, "CommissionDaily", 0),
            commission_monthly=safe_get(daily_obj, "CommissionMonthly", 0),
            agent_daily=safe_get(daily_obj, "AgentDaily", 0),
            agent_monthly=safe_get(daily_obj, "AgentMonthly", 0),
            balance_prev_day=safe_get(daily_obj, "BalancePrevDay", 0),
            balance_prev_month=safe_get(daily_obj, "BalancePrevMonth", 0),
            equity_prev_day=safe_get(daily_obj, "EquityPrevDay", 0),
            equity_prev_month=safe_get(daily_obj, "EquityPrevMonth", 0),
            margin=safe_get(daily_obj, "Margin", 0),
            margin_free=safe_get(daily_obj, "MarginFree", 0),
            margin_level=safe_get(daily_obj, "MarginLevel", 0),
            margin_leverage=safe_get(daily_obj, "MarginLeverage", 0),
            profit=safe_get(daily_obj, "Profit", 0),
            profit_storage=safe_get(daily_obj, "ProfitStorage", 0),
            profit_commission=safe_get(daily_obj, "ProfitCommission", 0),
            profit_equity=safe_get(daily_obj, "ProfitEquity", 0),
            profit_assets=safe_get(daily_obj, "ProfitAssets", 0),
            profit_liabilities=safe_get(daily_obj, "ProfitLiabilities", 0),
            daily_profit=safe_get(daily_obj, "DailyProfit", 0),
            daily_balance=safe_get(daily_obj, "DailyBalance", 0),
            daily_credit=safe_get(daily_obj, "DailyCredit", 0),
            daily_charge=safe_get(daily_obj, "DailyCharge", 0),
            daily_correction=safe_get(daily_obj, "DailyCorrection", 0),
            daily_bonus=safe_get(daily_obj, "DailyBonus", 0),
            daily_storage=safe_get(daily_obj, "DailyStorage", 0),
            daily_comm_instant=safe_get(daily_obj, "DailyCommInstant", 0),
            daily_comm_round=safe_get(daily_obj, "DailyCommRound", 0),
            daily_comm_fee=safe_get(daily_obj, "DailyCommFee", 0),
            daily_dividend=safe_get(daily_obj, "DailyDividend", 0),
            daily_taxes=safe_get(daily_obj, "DailyTaxes", 0),
            daily_so_compensation=safe_get(daily_obj, "DailySOCompensation", 0),
            daily_so_compensation_credit=safe_get(daily_obj, "DailySOCompensationCredit", 0),
            daily_agent=safe_get(daily_obj, "DailyAgent", 0),
            daily_interest=safe_get(daily_obj, "DailyInterest", 0),
        )
    )
    return daily


class DailySink:
    def OnDailyAdd(self, daily: MT5Manager.MTDaily):
        print("Daily Added", safe_get(daily, "Login"))
        save_mt5_daily(daily)
    
    def OnDailyUpdate(self, daily: MT5Manager.MTDaily):
        print("Daily Updated", safe_get(daily, "Login"))
        save_mt5_daily(daily)

    def OnDailyDelete(self, daily: MT5Manager.MTDaily):
        print("Daily Deleted", safe_get(daily, "Login"))
        MT5Daily.objects.filter(
            login=safe_get(daily, "Login"),
            datetime=safe_get(daily, "Datetime")
        ).delete()
    
    def OnDailyClean(self, daily: MT5Manager.MTDaily):
        print("Daily Clean", safe_get(daily, "Login"))
        MT5Daily.objects.filter(login=safe_get(daily, "Login")).delete()
