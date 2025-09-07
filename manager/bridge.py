import os, dotenv, logging, time
import MT5Manager
from .sinks.position import PositionSink
from .sinks.deal import DealSink
from .sinks.user import UserSink
from .sinks.order import OrderSink
from .sinks.account import AccountSink
from .sinks.summary import SummarySink
from .sinks.daily import DailySink
from .sinks.tick import TickSink
from trading.models import MT5User, RuleViolationLog
from challenge.models import PropFirmChallenge
from datetime import datetime, timedelta
from django.utils import timezone
from collections import defaultdict
from enum import Enum
from typing import List, Dict
from .account_manager import AccountManager

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

class ViolationSeverity(Enum):
    WARNING = "WARNING"
    SEVERE = "SEVERE"
    CRITICAL = "CRITICAL"

class AccountAction(Enum):
    DISABLE_LOGIN = "DISABLE_LOGIN"
    CLOSE_POSITIONS = "CLOSE_POSITIONS"
    MOVE_TO_DISABLED_GROUP = "MOVE_TO_DISABLED_GROUP"
    ACCOUNT_CLOSED = "ACCOUNT_CLOSED"

class MetaTraderBridge:
    def __init__(self, address, login, password, user_group):
        self.address = address
        self.login = int(login)
        self.password = password
        self.user_group = user_group
        self.manager = MT5Manager.ManagerAPI()
        self.local_account_manager = AccountManager()
        
        # Violation tracking
        self.violation_counts = defaultdict(lambda: defaultdict(int))  # login -> severity -> count
        self.last_violation_check = defaultdict(datetime)  # login -> last check time
        
        # Violation thresholds for account actions
        self.violation_thresholds = {
            ViolationSeverity.WARNING: 10,    # 10 warnings in timeframe
            ViolationSeverity.SEVERE: 3,      # 3 severe violations
            ViolationSeverity.CRITICAL: 1     # 1 critical violation = immediate closure
        }
        
        # Time window for violation accumulation (24 hours)
        self.violation_window = timedelta(hours=24)

    def connect(self):
        self._subscribe_sinks()
        connected = self.manager.Connect(
            self.address,
            self.login,
            self.password,
            MT5Manager.ManagerAPI.EnPumpModes.PUMP_MODE_FULL
        )

        if not connected:
            print(f"Failed to connect: {MT5Manager.LastError()}")
            return False

        print("Connected to MT5 Manager API")
        return True

    def disconnect(self):
        print("Disconnecting from MT5...")
        return self.manager.Disconnect()

    def _subscribe_sinks(self):
        """Subscribe to all data sinks with bridge reference"""
        if not self.manager.UserSubscribe(UserSink()):
            print(f"UserSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.PositionSubscribe(PositionSink(self)):
            print(f"PositionSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.DealSubscribe(DealSink(self)):
            print(f"DealSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.OrderSubscribe(OrderSink()):
            print(f"OrderSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.UserAccountSubscribe(AccountSink(self)):
            print(f"AccountSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.TickSubscribe(TickSink()):
            print(f"TickSubscribe failed: {MT5Manager.LastError()}")

        print("All sinks subscribed successfully")

    def get_user(self, login)->MT5Manager.MTUser:
       return self.manager.UserGet(login)
    
    def delete_user(self, login)->MT5Manager.MTUser:
        return self.manager.UserDelete(login)
    
    def get_account(self, login)->MT5Manager.MTAccount:
        return self.manager.UserAccountGet(login)
    
    def challenge_passed(self, login):
        self.local_account_manager.close_account(login, 'challenge_passed')
        self._close_account(login)
        print("Challenge Passed")

    def challenge_failed(self, login):
        self.local_account_manager.close_account(login, 'failed')
        self._close_account(login)
        print("Challenge Failed")

    def handle_violation(self, login: int, violations: List[str], violation_source: str = ""):
        """Handle rule violations with accumulation logic"""
        if not violations:
            return
            
        # Categorize violations by severity
        categorized_violations = self._categorize_violations(violations)
        print("Logging Violations")
        self._log_violation_accumulation(login, categorized_violations, violation_source)


    def _categorize_violations(self, violations: List[str]) -> Dict[ViolationSeverity, List[str]]:
        """Categorize violations by severity level"""
        categorized = {
            ViolationSeverity.WARNING: [],
            ViolationSeverity.SEVERE: [],
            ViolationSeverity.CRITICAL: []
        }
        
        for violation in violations:
            if any(keyword in violation for keyword in ["DRAWDOWN_EXCEEDED", "DAILY_LOSS_EXCEEDED"]):
                categorized[ViolationSeverity.CRITICAL].append(violation)
            elif any(keyword in violation for keyword in [
                "RISK_EXCEEDED", "NO_STOP_LOSS", "SYMBOL_LIMIT", "OVERALL_RISK_EXCEEDED", "POSITIONS_WITHOUT_STOPS", 
                "MARTINGALE_DETECTED", "GRID_DETECTED", "HEDGING_DETECTED"
            ]):
                categorized[ViolationSeverity.SEVERE].append(violation)
            elif any(keyword in violation for keyword in ["DRAWDOWN_WARNING", "DAILY_LOSS_WARNING"]):
                categorized[ViolationSeverity.WARNING].append(violation)
            else:
                # Default to severe for unknown violations
                categorized[ViolationSeverity.SEVERE].append(violation)
                
        return categorized

    def _close_account(self, login: int):
        """Close/disable MT5 account due to rule violations"""
        try:
            print(f"Closing account {login} due to rule violations")
            # 1. Get user info
            user_info = MT5Manager.MTUser()
            if not self.manager.UserGet(login, user_info):
                print(f"Failed to get user info for {login}: {MT5Manager.LastError()}")
                return False
                
            # 2. Close all open positions first
            self._close_all_positions(login)
            
            # 3. Move to disabled group (assuming you have a disabled group)
            # user_info.Group = "\\Disabled\\"  # Adjust group name as needed
            user_info.Rights = 0  # Remove all rights
            
            if not self.manager.UserUpdate(user_info):
                print(f"Failed to update user {login}: {MT5Manager.LastError()}")
                return False
            
            print(f"Account {login} successfully closed and moved to disabled group")
            return True
            
        except Exception as e:
            print(f"Error closing account {login}: {e}")
            return False

    def _close_hedge_position(self, login, position_id, caused_position_id):
        print("Close hedge")

    def _close_all_positions(self, login: int):
        """Close all open positions for an account"""
        try:
            # Get all open positions
            positions = self.manager.PositionGet(login)
            for position in positions:
                result = self.manager.PositionDelete(position)
                if not result:
                    print(f"Failed to close position {position.Position}")
                        
        except Exception as e:
            print(f"Error closing positions for {login}: {e}")


    def _log_violation_accumulation(self, login: int, categorized_violations: Dict[ViolationSeverity, List[str]], source: str):
        """Log violations that don't trigger closure yet"""
        for severity, violation_list in categorized_violations.items():
            for violation in violation_list:
                try:
                    RuleViolationLog.objects.create(
                        login=login,
                        severity=severity.value,
                        violation_type=f"{severity.value}_{source}",
                        message=f"{severity.value}: {violation}",
                        timestamp=timezone.now()
                    )
                except Exception as e:
                    print(f"Failed to log violation: {e}")