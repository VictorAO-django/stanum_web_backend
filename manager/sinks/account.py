import MT5Manager
from trading.models import MT5Account, MT5AccountHistory
from manager.rule_checker import RuleChecker
from manager.helper import trigger_account_closure
from django.utils import timezone

rule_checker = RuleChecker()

def _should_record_history(previous_equity: float, current_equity: float) -> bool:
    """Determine if we should create a history record"""
    if previous_equity == 0:
        return True  # First record
    # Calculate percentage change
    equity_change_percent = abs(current_equity - previous_equity) / previous_equity * 100
    # Record if >1% change or >$100 absolute change
    return equity_change_percent >= 1.0 or abs(current_equity - previous_equity) >= 100

def _create_account_history(account_obj: MT5Manager.MTAccount):
    """Create historical account record"""
    try:
        MT5AccountHistory.objects.create(
            login=account_obj.Login,
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
            # timestamp=timezone.now(),
        )
        print(f"Created history record for account {account_obj.Login}, equity: {account_obj.Equity}")
    except Exception as e:
        print(f"Failed to create account history for {account_obj.Login}: {e}")


def save_mt5_account(account_obj: MT5Manager.MTAccount):
    """Save current account state and create history record if needed"""
    # Get previous account state for comparison
    try:
        previous_account = MT5Account.objects.get(login=account_obj.Login)
        previous_equity = float(previous_account.equity)
    except MT5Account.DoesNotExist:
        previous_account = None
        previous_equity = 0
    
    # Update current account state
    account, created = MT5Account.objects.update_or_create(
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
            updated_at=timezone.now(),
        )
    )
    
    current_equity = float(account_obj.Equity)
    
    # Create history record if:
    # 1. New account (created=True)
    # 2. Significant equity change (>1% or >$100)
    # 3. Critical events (margin call, stop out)
    # should_create_history = (
    #     created or 
    #     _should_record_history(previous_equity, current_equity)
    # )
    
    # if should_create_history:
    #     _create_account_history(account_obj)
    
    return account

class AccountSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.rule_checker = RuleChecker()
    
    def OnAccountMarginCallEnter(self, account: MT5Manager.MTAccount, group: MT5Manager.MTConGroup):
        print("Account entering the Margin Call state", account.Login)
        
        # Save account state and create history record
        save_mt5_account(account)
        
        # Check account rules for margin call situations
        violations = self.rule_checker.check_account_rules(account)
        
        if violations and self.bridge:
            self.bridge.handle_violation(account.Login, violations, "MARGIN_CALL_ENTER")
        
        # Additional margin call specific violation
        margin_call_violation = [f"MARGIN_CALL_ENTERED: Margin level {account.MarginLevel}%"]
        if self.bridge:
            self.bridge.handle_violation(account.Login, margin_call_violation, "MARGIN_CALL")

    def OnAccountMarginCallLeave(self, account: MT5Manager.MTAccount, group: MT5Manager.MTConGroup):
        print("Account exiting the Margin Call state", account.Login)
        
        save_mt5_account(account)
        
        # Log recovery from margin call
        recovery_log = [f"MARGIN_CALL_RECOVERY: Margin level restored to {account.MarginLevel}%"]
        if self.bridge:
            self.bridge.handle_violation(account.Login, recovery_log, "MARGIN_CALL_RECOVERY")

    def OnAccountStopOutEnter(self, account: MT5Manager.MTAccount, group: MT5Manager.MTConGroup):
        print("Account entering the Stop Out state", account.Login)
        
        save_mt5_account(account)
        
        # Stop out is critical - check all rules
        violations = self.rule_checker.check_account_rules(account)
        
        # Add stop out specific critical violation
        stop_out_violation = [f"STOP_OUT_ENTERED: Critical margin level {account.MarginLevel}%"]
        violations.extend(stop_out_violation)
        
        if violations and self.bridge:
            self.bridge.handle_violation(account.Login, violations, "STOP_OUT_ENTER")
    
    def OnAccountStopOutLeave(self, account: MT5Manager.MTAccount, group: MT5Manager.MTConGroup):
        print("Account exiting the Stop Out state", account.Login)
        
        save_mt5_account(account)
        
        # Log recovery from stop out
        recovery_log = [f"STOP_OUT_RECOVERY: Account recovered, margin level: {account.MarginLevel}%"]
        if self.bridge:
            self.bridge.handle_violation(account.Login, recovery_log, "STOP_OUT_RECOVERY")
    
    def OnAccountUpdate(self, account: MT5Manager.MTAccount):
        """Handle general account updates - add this if MT5 provides this callback"""
        # Save account state (history will be created if significant change)
        print("Account update", account.Login)
        save_mt5_account(account)
        # Check drawdown and daily loss rules on every significant update
        violations = self.rule_checker.check_account_rules(account)
        
        if violations and self.bridge:
            self.bridge.handle_violation(account.Login, violations, "ACCOUNT_UPDATE")