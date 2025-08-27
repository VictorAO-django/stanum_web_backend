import MT5Manager
from trading.models import MT5Account

def save_mt5_account(account_obj:MT5Manager.MTAccount):
    account, _ = MT5Account.objects.update_or_create(
        login=account_obj.Login,
        defaults=dict(
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
        )
    )
    return account

class AccountSink:
    def OnAccountMarginCallEnter(self, account:MT5Manager.MTAccount, group:MT5Manager.MTConGroup):
        print("account entering the Margin Call state", account.Login)
        save_mt5_account(account)

    def OnAccountMarginCallLeave(self, account:MT5Manager.MTAccount, group:MT5Manager.MTConGroup):
        print("account exiting the Margin Call state", account.Login)
        save_mt5_account(account)

    def OnAccountStopOutEnter(self, account:MT5Manager.MTAccount, group:MT5Manager.MTConGroup):
        print("account entering the Stop Out state", account.Login)
        save_mt5_account(account)
    
    def OnAccountStopOutLeave(self, account:MT5Manager.MTAccount, group:MT5Manager.MTConGroup):
        print("account exiting the Stop Out state", account.Login)
        save_mt5_account(account)