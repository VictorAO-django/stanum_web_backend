import MT5Manager
from challenge.models import PropFirmChallenge
from datetime import datetime, timedelta
from django.utils.timezone import now
from decimal import Decimal
from django.db.models import Q, Count, Sum
from django.utils import timezone
from typing import List

from .InMemoryData import *

from .logging_config import get_prop_logger
import time
logger = get_prop_logger('rules')

class InMemoryRuleChecker:
    """In-memory rule checker that persists across bridge restarts"""
    
    def check_account_rules(self, account: AccountData, challenge: PropFirmChallenge, daily_drawdown:DailyDrawdownData=None, total_drawdown:AccountTotalDrawdownData=None) -> List[ViolationDict]:
        """Check account-level rules (drawdown, daily loss)"""
        violations:List[ViolationDict] = []
        # print("Checking Violations")
        if not challenge:
            return violations
        
        try:
            #Check if the challenge class is a funded or not
            if challenge.challenge_class not in ['skill_check_funding', 'challenge_funding']:
                violations.extend(self._check_max_days(account, challenge))
            if account.step != 2:
                violations.extend(self._check_daily_drawdown(account, challenge, daily_drawdown))
            # print("checking")
            violations.extend(self._check_total_drawdown(account, challenge, total_drawdown))
            # print("checking2")
            # print("Done Checking Violations", account.login, violations)
            return violations
        except Exception as err:
            print("Error", str(err))
    
    def _check_hft(self, deals: List[DealData], challenge: PropFirmChallenge) -> List[ViolationDict]:
        """Check for High Frequency Trading using provided deals list"""
        violations: List[ViolationDict] = []

        current_time_unix = int(time.time())
        one_minute_ago = current_time_unix - 60
        one_hour_ago = current_time_unix - 3600

        # Filter only real entry deals (buy/sell with entry IN or INOUT)
        deals = [
            d for d in deals 
            if (d.action in [0, 1]) and (d.entry in [0, 2])
        ]

        # Count deals in the last minute/hour for this login
        recent_trades_count_1_min = sum(1 for d in deals if  d.time and d.time >= one_minute_ago)
        recent_trades_count_1_hr = sum(1 for d in deals if d.time and d.time >= one_hour_ago)

        if recent_trades_count_1_min > challenge.max_trades_per_minute:
            violations.append(
                {"type": "HFT_MINUTE_VIOLATION", "message": f"{recent_trades_count_1_min} trades in 1 minute (limit: {challenge.max_trades_per_minute})"}
            )

        if recent_trades_count_1_hr > challenge.max_trades_per_hour:
            violations.append(
                {"type": "HFT_HOUR_VIOLATION", "message": f"{recent_trades_count_1_hr} trades in 1 hour (limit: {challenge.max_trades_per_hour})"}
            )

        return violations

    
    def _check_symbol_limit(self, position:PositionData, positions:List[PositionData], challenge: PropFirmChallenge) -> List[ViolationDict]:
        """Check positions per symbol using database"""
        violations:List[ViolationDict] = []
        
        # Count existing positions for this symbol (excluding the current one being added)
        count = sum(1 for p in positions if p.symbol == position.symbol and p.position_id != position.position_id)
        # Add 1 for the current position being added
        total_count = count + 1

        max_positions_per_symbol = challenge.max_orders_per_symbol
        if total_count > max_positions_per_symbol:
            violations.append(
                {"type": "SYMBOL_LIMIT", "message": f"{count} positions on {position.symbol} (max: {max_positions_per_symbol})"}
            )
                
        return violations
    
    def _check_prohibited_strategies(self, deals: List[DealData], challenge: "PropFirmChallenge") -> List[ViolationDict]:
        """Detects prohibited strategies such as Grid and Martingale. Returns a list of detected violations."""

        violations:List[ViolationDict] = []

        # Filter only relevant "entry" deals (open/in-out trades)
        open_deals = [
            d for d in deals
            if (d.action in [0, 1]) and (d.entry in [0, 2])  # buy/sell + entry
        ]
        if not open_deals:
            return violations

        #Sort by time to process sequentially
        open_deals.sort(key=lambda d: d.time)

        # =========================================================
        # GRID DETECTION
        # Logic: multiple trades (3+) opened close in time with same lot size.
        # Often across same symbol, but we can check globally too.
        # =========================================================
        if not challenge.grid_trading_allowed and len(open_deals) >= 3:
            last_3 = open_deals[-3:]
            volumes = [float(d.volume) for d in last_3]

            if len(set(volumes)) == 1:
                # optionally, you can check same symbol:
                # symbols = {d.symbol for d in last_3}
                # if len(symbols) == 1:
                violations.append(
                    {"type": "GRID_DETECTED", "message": f"3+ trades with equal volume ({volumes[0]})"}
                )

        # =========================================================
        # MARTINGALE DETECTION
        # Logic: lot size increases after a losing trade.
        # Classic martingale = "if previous trade lost, increase next volume".
        # =========================================================
        if not challenge.martingale_allowed and len(open_deals) >= 2:
            for prev, curr in zip(open_deals[:-1], open_deals[1:]):
                prev_loss = prev.profit < 0
                increased_lot = curr.volume > prev.volume

                if prev_loss and increased_lot:
                    violations.append(
                        {"type": "MARTINGALE_DETECTED", "message": f"Lot increased from {prev.volume} - {curr.volume} after a loss"}
                    )
                    break  # one detection is enough

        return violations
    
    
    def _check_min_days(self, account: AccountData, challenge: PropFirmChallenge) -> list[str]:
        """Check if minimum trading days have been met."""

        min_days = challenge.min_trading_days or 0
        account_created_at = account.created_at.date()
        today = now().date()
        days_elapsed = (today - account_created_at).days

        return days_elapsed > min_days
    
    def _check_challenge_period(self, account: AccountData, challenge: PropFirmChallenge):
        """Check if challenge period has exceeded allocated days."""
        violations = []

        # Allowed duration
        max_days = challenge.max_trading_days
        additional_days = challenge.additional_trading_days or 0
        total_allowed_days = max_days + additional_days
        # print("CHALLENGE PERIOD", max_days)
        # When the account started
        account_created_at = account.created_at.date()
        today = now().date()

        # Days passed since creation
        days_elapsed = (today - account_created_at).days

        # Checks
        if days_elapsed > total_allowed_days:
            violations.append(
                f"MAX_DAYS_EXCEEDED: {days_elapsed} > allowed {total_allowed_days}"
            )
        elif days_elapsed < challenge.min_trading_days:
            violations.append(
                f"MIN_DAYS_NOT_REACHED: {days_elapsed}/{challenge.min_trading_days}"
            )
        # print("DONE CHECKING PERIOD")
        return violations

    def _check_max_days(self, account: AccountData, challenge: PropFirmChallenge) -> list[ViolationDict]:
        """Check if account has exceeded max trading days (including extensions)."""
        violations:List[ViolationDict] = []

        max_days = challenge.max_trading_days or 0
        additional_days = challenge.additional_trading_days or 0
        total_allowed_days = max_days + additional_days

        account_created_at = account.created_at.date()
        today = now().date()
        days_elapsed = (today - account_created_at).days

        if days_elapsed > total_allowed_days:
            violations.append(
                {"type": "MAX_DAYS_EXCEEDED", "message": f"{days_elapsed} > allowed {total_allowed_days}"}
            )

        return violations

    def _check_daily_drawdown(self, account: AccountData, challenge: PropFirmChallenge, dd: DailyDrawdownData) -> list[ViolationDict]:
        """Check drawdown limits using tracked high-watermark equity."""
        # print("CHECKING DAILY DRAWSOWN", dd)
        violations:List[ViolationDict] = []
        if not dd:
            # No record yet, safe to assume no violation
            return violations
        
        current_dd_percent = float(dd.drawdown_percent)
        max_dd = float(challenge.max_daily_loss_percent)
        if current_dd_percent > max_dd:
            violations.append({ "type": "DAILY_DRAWDOWN_EXCEEDED", "message": f"{current_dd_percent:.2f}% (max: {max_dd}%)"})

        # print("DONE CHECKING DAILY DRAWSOWN")
        return violations
        
    def _check_total_drawdown(
        self,
        account: AccountData,
        challenge: PropFirmChallenge,
        total_dd: AccountTotalDrawdownData
    ) -> List[ViolationDict]:
        """
        Check overall drawdown using AccountTotalDrawdown model.
        """
        violations: List[ViolationDict] = []
        if not total_dd:
            # No record yet, safe to assume no violation
            return violations

        current_dd_percent = float(total_dd.drawdown_percent)
        max_dd = (
            float(challenge.max_total_loss_percent)
            if account.step == 1
            else float(challenge.additional_phase_total_loss_percent)
        )

        if current_dd_percent > max_dd:
            violations.append(
                {
                    "type": "TOTAL_DRAWDOWN_EXCEEDED",
                    "message": f"{current_dd_percent:.2f}% (max: {max_dd}%)"
                }
            )

        return violations

    
    def _check_profit(self, account: AccountData, challenge: PropFirmChallenge) -> bool:
        """Check if account has reached the profit target."""
        # logger.info(f"CHECKING PROFIT {account.login}")
        current_profit = account.profit
        if account.step == 2:
            target_profit_amount = (challenge.phase_2_profit_target_percent / Decimal(100)) * challenge.account_size
        else:
            target_profit_amount = (challenge.profit_target_percent / Decimal(100)) * challenge.account_size

        # if (account.login == 4005):
        #     logger.info(f"CURRENT PROFIT-{current_profit} TARGET PROFIT-{target_profit_amount}")
        

        # Check if profit target is reached
        return current_profit >= target_profit_amount