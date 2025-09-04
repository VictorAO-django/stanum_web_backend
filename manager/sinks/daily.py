import MT5Manager
from datetime import datetime
from django.utils import timezone
from trading.models import MT5Daily

def convert_time(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None

def save_mt5_daily(daily_obj:MT5Manager.MTDaily):
    """
    Save or update MT5Daily record from an MTDaily object (MT5 Manager API).
    """
    daily, _ = MT5Daily.objects.update_or_create(
        login=daily_obj.Login,
        datetime=convert_time(daily_obj.Datetime),  # <-- FIXED
        defaults=dict(
            datetime_prev=convert_time(getattr(daily_obj, "DatetimePrev", 0)),
            name=getattr(daily_obj, "Name", None),
            group=getattr(daily_obj, "Group", None),
            currency=getattr(daily_obj, "Currency", None),
            currency_digits=getattr(daily_obj, "CurrencyDigits", 2),
            company=getattr(daily_obj, "Company", None),
            email=getattr(daily_obj, "Email", None),

            balance=getattr(daily_obj, "Balance", 0),
            credit=getattr(daily_obj, "Credit", 0),
            interest_rate=getattr(daily_obj, "InterestRate", 0),
            commission_daily=getattr(daily_obj, "CommissionDaily", 0),
            commission_monthly=getattr(daily_obj, "CommissionMonthly", 0),
            agent_daily=getattr(daily_obj, "AgentDaily", 0),
            agent_monthly=getattr(daily_obj, "AgentMonthly", 0),

            balance_prev_day=getattr(daily_obj, "BalancePrevDay", 0),
            balance_prev_month=getattr(daily_obj, "BalancePrevMonth", 0),
            equity_prev_day=getattr(daily_obj, "EquityPrevDay", 0),
            equity_prev_month=getattr(daily_obj, "EquityPrevMonth", 0),

            margin=getattr(daily_obj, "Margin", 0),
            margin_free=getattr(daily_obj, "MarginFree", 0),
            margin_level=getattr(daily_obj, "MarginLevel", 0),
            margin_leverage=getattr(daily_obj, "MarginLeverage", 1),

            profit=getattr(daily_obj, "Profit", 0),
            profit_storage=getattr(daily_obj, "ProfitStorage", 0),
            profit_commission=getattr(daily_obj, "ProfitCommission", 0),
            profit_equity=getattr(daily_obj, "ProfitEquity", 0),
            profit_assets=getattr(daily_obj, "ProfitAssets", 0),
            profit_liabilities=getattr(daily_obj, "ProfitLiabilities", 0),

            daily_profit=getattr(daily_obj, "DailyProfit", 0),
            daily_balance=getattr(daily_obj, "DailyBalance", 0),
            daily_credit=getattr(daily_obj, "DailyCredit", 0),
            daily_charge=getattr(daily_obj, "DailyCharge", 0),
            daily_correction=getattr(daily_obj, "DailyCorrection", 0),
            daily_bonus=getattr(daily_obj, "DailyBonus", 0),
            daily_storage=getattr(daily_obj, "DailyStorage", 0),
            daily_comm_instant=getattr(daily_obj, "DailyCommInstant", 0),
            daily_comm_round=getattr(daily_obj, "DailyCommRound", 0),
            daily_comm_fee=getattr(daily_obj, "DailyCommFee", 0),
            daily_dividend=getattr(daily_obj, "DailyDividend", 0),
            daily_taxes=getattr(daily_obj, "DailyTaxes", 0),
            daily_so_compensation=getattr(daily_obj, "DailySOCompensation", 0),
            daily_so_compensation_credit=getattr(daily_obj, "DailySOCompensationCredit", 0),
            daily_agent=getattr(daily_obj, "DailyAgent", 0),
            daily_interest=getattr(daily_obj, "DailyInterest", 0),
        )
    )
    return daily


class DailySink:
    def OnDailyAdd(self, daily: MT5Manager.MTDaily):
        print("Daily Added", daily.Login)
        save_mt5_daily(daily)
    
    def OnDailyUpdate(self, daily: MT5Manager.MTDaily):
        print("Daily Updated", daily.Login)
        save_mt5_daily(daily)

    def OnDailyDelete(self, daily: MT5Manager.MTDaily):
        print("Daily Deleted", daily.Login)
        MT5Daily.objects.filter(
            login=daily.Login,
            datetime=convert_time(daily.Datetime)
        ).update(deleted=True)
    
    def OnDailyClean(self, login):
        print("Daily Clean", login)
        MT5Daily.objects.filter(login=login).update(
            deleted = True
        )
