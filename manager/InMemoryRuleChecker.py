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
logger = get_prop_logger('rules')

class InMemoryRuleChecker:
    """In-memory rule checker that persists across bridge restarts"""

    def check_position_rules(self, position: MT5Manager.MTPosition, account: MT5Manager.MTAccount) -> List[str]:
        """Check rules for a new deal"""
        print("Analysing position", position.Login)
        violations = []
        
        # if not challenge:
        #     return violations
        
        # user = MT5User.objects.get(login=position.Login)

        # # 1. Check HFT (High Frequency Trading)
        # violations.extend(self._check_hft(position, challenge))
        
        # # 2. Check risk per trade
        # violations.extend(self._check_risk_per_trade(position, challenge, user, account))
        
        # # 3 Check Overall Risk limit
        # violations.extend(self._check_overall_risk_limit(position, challenge, user, account))

        # # 3. Check symbol position limit (max 2 per symbol)
        # violations.extend(self._check_symbol_limit(position, challenge))
        
        # # 4. Check for grid/martingale patterns
        # violations.extend(self._check_prohibited_strategies(position, challenge))
        
        return violations
    
    def check_account_rules(self, account: AccountData, challenge: PropFirmChallenge, daily_drawdown:DailyDrawdownData=None, total_drawdown:AccountTotalDrawdownData=None) -> List[str]:
        """Check account-level rules (drawdown, daily loss)"""
        violations = []
        # print("Checking Violations")
        if not challenge:
            return violations
        
        try:
            # violations.extend(self._check_challenge_period(account, challenge))
            violations.extend(self._check_max_days(account, challenge))
            if account.step != 2:
                violations.extend(self._check_daily_drawdown(account, challenge, daily_drawdown))
            # print("checking")
            violations.extend(self._check_total_drawdown(account, challenge, total_drawdown))
            # print("checking2")
            print("Done Checking Violations", account.login, violations)
            return violations
        except Exception as err:
            print("Error", str(err))
    
    # def _check_hft(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
    #     """Check for High Frequency Trading using database queries"""
    #     violations = []
        
    #     # Count trades in last minute from database
    #     one_minute_ago = timezone.now() - timedelta(minutes=1)
    #     one_hour_ago = timezone.now() - timedelta(hours=1)
        
    #     recent_trades_count_1_min = MT5Position.objects.filter(login=position.Login, created_at__gte=one_minute_ago).count()
    #     recent_trades_count_1_hr = MT5Position.objects.filter(login=position.Login, created_at__gte=one_hour_ago).count()
        
    #     if recent_trades_count_1_min > challenge.max_trades_per_minute:
    #         violations.append(f"HFT_VIOLATION: {recent_trades_count_1_min} trades in 1 minute (limit: {challenge.max_trades_per_minute})")
        
    #     if recent_trades_count_1_hr > challenge.max_trades_per_hour:
    #         violations.append(f"HFT_VIOLATION: {recent_trades_count_1_hr} trades in 1 hour (limit: {challenge.max_trades_per_hour})")

    #     return violations
    

    # def _check_risk_per_trade(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge, user: MT5User, account: MT5Manager.MTAccount) -> List[str]:
    #     violations = []

    #     if account.Equity <= 0:
    #         return violations

    #     # Get position details
    #     volume = abs(float(position.Volume))
    #     price_open = float(position.PriceOpen)
    #     equity = float(account.Equity)
        
    #     # Calculate actual risk (you need stop loss for this)
    #     if hasattr(position, 'PriceSL') and position.PriceSL > 0:
    #         stop_loss = float(position.PriceSL)
            
    #         # Calculate risk per unit
    #         risk_per_unit = abs(price_open - stop_loss)
            
    #         # Calculate total risk amount
    #         pip_value = volume * risk_per_unit  # This may need adjustment based on instrument
    #         risk_amount = pip_value
            
    #         # Calculate risk as percentage of equity
    #         risk_percent = (risk_amount / equity) * 100
            
    #         print(f"DEBUG - Risk Amount: {risk_amount}, Risk Percent: {risk_percent}%")
            
    #         max_risk = challenge.max_risk_per_trade_percent
            
    #         if risk_percent > max_risk:
    #             violations.append(f"RISK_EXCEEDED: {risk_percent:.2f}% risk (max: {max_risk}%)")
    #     else:
    #         # If no stop loss, you might want to flag this as unlimited risk
    #         violations.append("NO_STOP_LOSS: Position has unlimited risk")
            
    #     return violations
    
    
    # def _check_overall_risk_limit(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge, user: MT5User, account: MT5Manager.MTAccount) -> List[str]:
    #     """Check overall risk across all open positions"""
    #     violations = []
        
    #     if account.Equity <= 0:
    #         return violations
        
    #     # Get all current open positions for this login
    #     all_positions = MT5Position.objects.filter(login=position.Login, closed=False)
        
    #     total_risk_amount = 0
    #     positions_without_stops = 0
        
    #     for pos in all_positions:
    #         volume = abs(float(pos.volume))
    #         price_open = float(pos.price_open)
            
    #         # Calculate actual risk based on stop loss
    #         if hasattr(pos, 'price_sl') and pos.price_sl and float(pos.price_sl) > 0:
    #             stop_loss = float(pos.price_sl)
                
    #             # Risk per unit (distance to stop loss)
    #             risk_per_unit = abs(price_open - stop_loss)
                
    #             # Total risk for this position
    #             position_risk = volume * risk_per_unit  # May need adjustment for different instruments
    #             total_risk_amount += position_risk
                
    #         else:
    #             # Position without stop loss = unlimited risk
    #             positions_without_stops += 1
        
    #     # Calculate total risk percentage
    #     total_risk_percent = (total_risk_amount / float(account.Equity)) * 100
        
    #     print(f"DEBUG - Total Risk Amount: {total_risk_amount}, Total Risk %: {total_risk_percent}%")
        
    #     max_overall_risk = challenge.overall_risk_limit_percent
        
    #     if total_risk_percent > max_overall_risk:
    #         violations.append(f"OVERALL_RISK_EXCEEDED: {total_risk_percent:.2f}% total risk (max: {max_overall_risk}%)")
        
    #     if positions_without_stops > 0:
    #         violations.append(f"POSITIONS_WITHOUT_STOPS: {positions_without_stops} positions have unlimited risk")
        
    #     return violations
    
    # def _check_symbol_limit(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
    #     """Check max 2 positions per symbol using database"""
    #     violations = []
        
    #     # Count current open positions for this symbol
    #     current_positions = MT5Position.objects.filter(
    #         login=position.Login,
    #         symbol=position.Symbol,
    #         closed=False
    #     ).count()
        
    #     max_positions_per_symbol = challenge.max_orders_per_symbol
        
    #     if current_positions > max_positions_per_symbol:
    #         violations.append(f"SYMBOL_LIMIT: {current_positions} positions on {position.Symbol} (max: {max_positions_per_symbol})")
                
    #     return violations
    
    # def _check_prohibited_strategies(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
    #     """Basic grid/martingale/hedging detection using database queries"""
    #     violations = []
        
    #     # Get recent positions for this login (last 24 hours)
    #     positions = MT5Position.objects.filter(
    #         login=position.Login,
    #         closed=False
    #     ).order_by('-created_at')
        
    #     if not challenge.grid_trading_allowed:
    #         if positions.count() >= 3:
    #             positions_list = list(positions)
                
    #             # Simple grid detection: 3+ trades with same volume
    #             volumes = [float(d.volume) for d in positions_list]
    #             if len(set(volumes)) == 1:  # All same volume
    #                 violations.append(f"GRID_DETECTED: Equal volumes ({volumes[0]}) on {position.Symbol}")
        
    #     if not challenge.martingale_allowed:
    #         # Simple martingale detection: check if volume doubled after loss
    #         if positions.count() >= 2:
    #             positions_list = list(positions)
    #             previous_position = positions_list[1]  # Second most recent
                
    #             if (float(previous_position.profit) < 0 and  # Previous trade was loss
    #                 float(position.Volume) >= float(previous_position.volume) * 1.8):  # Current volume ~doubled
    #                 violations.append(f"MARTINGALE_DETECTED: Volume increase after loss on {position.Symbol}")
        
    #     if not challenge.hedging_within_account_allowed:
    #         # Hedging detection: Check for opposing positions on same symbol
    #         current_positions = MT5Position.objects.filter(
    #             login=position.Login,
    #             symbol=position.Symbol
    #         ).exclude(position_id=position.Position)  # Exclude current position
            
    #         for existing_pos in current_positions:
    #             # Check if positions are opposing (different action types)
    #             if existing_pos.action != position.Action:  # 0=BUY, 1=SELL
    #                 violations.append(f"HEDGING_DETECTED: Opposing positions on {position.Symbol} - Current: {'BUY' if position.Action == 0 else 'SELL'}, Existing: {'BUY' if existing_pos.action == 0 else 'SELL'}")
    #                 break  # Only report once per symbol
                    
    #     return violations
    
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
                f"MAX DAYS EXCEEDED: {days_elapsed} > allowed {total_allowed_days}"
            )
        elif days_elapsed < challenge.min_trading_days:
            violations.append(
                f"MIN DAYS NOT REACHED: {days_elapsed}/{challenge.min_trading_days}"
            )
        # print("DONE CHECKING PERIOD")
        return violations

    def _check_max_days(self, account: AccountData, challenge: PropFirmChallenge) -> list[str]:
        """Check if account has exceeded max trading days (including extensions)."""
        violations = []

        max_days = challenge.max_trading_days or 0
        additional_days = challenge.additional_trading_days or 0
        total_allowed_days = max_days + additional_days

        account_created_at = account.created_at.date()
        today = now().date()
        days_elapsed = (today - account_created_at).days

        if days_elapsed > total_allowed_days:
            violations.append(
                f"MAX DAYS EXCEEDED: {days_elapsed} > allowed {total_allowed_days}"
            )

        return violations

    def _check_daily_drawdown(self, account: AccountData, challenge: PropFirmChallenge, dd: DailyDrawdownData) -> list[str]:
        """Check drawdown limits using tracked high-watermark equity."""
        # print("CHECKING DAILY DRAWSOWN", dd)
        violations = []

        if dd:
            equity_peak = float(dd.equity_high)
        else:
            # fallback: initial balance or current equity if no record exists yet
            equity_peak = max(float(account.equity), float(challenge.account_size))

        current_equity = float(account.equity)

        # Calculate drawdown %
        if equity_peak > 0:
            current_dd_percent = ((equity_peak - current_equity) / equity_peak) * 100
        else:
            current_dd_percent = 0

        max_dd = float(challenge.max_total_loss_percent)

        if current_dd_percent > max_dd:
            violations.append(
                f"DAILY_DRAWDOWN_EXCEEDED: {current_dd_percent:.2f}% (max: {max_dd}%)"
            )
        # elif current_dd_percent > max_dd * 0.8:  # 80% warning threshold
        #     violations.append(
        #         f"DAILY_DRAWDOWN_WARNING: {current_dd_percent:.2f}% (limit: {max_dd}%)"
        #     )

        # print("DONE CHECKING DAILY DRAWSOWN")
        return violations
        
    def _check_total_drawdown(self, account: AccountData, challenge: PropFirmChallenge, total_dd: AccountTotalDrawdownData) -> List[str]:
        """
        Check overall drawdown using AccountTotalDrawdown model.
        """
        # print("CHECKING TOTALDRAWDOWN", total_dd)
        violations = []
        current_equity = account.equity

        # Update peak/low and recalc drawdown
        if current_equity > total_dd.equity_peak:
            total_dd.equity_peak = current_equity
            total_dd.equity_low = current_equity
        elif current_equity < total_dd.equity_low:
            total_dd.equity_low = current_equity

        if total_dd.equity_peak > 0:
            total_dd.drawdown_percent = ((total_dd.equity_peak - total_dd.equity_low) / total_dd.equity_peak) * 100

        # 2. Calculate allowed minimum equity
        max_dd_percent = challenge.max_total_loss_percent if account.step == 1 else challenge.additional_phase_total_loss_percent
        min_allowed_equity = total_dd.equity_peak * (1 - max_dd_percent / 100)

        # 3. Compare current equity to limits
        if current_equity < min_allowed_equity:
            violations.append(
                f"TOTAL_DRAWDOWN_EXCEEDED: Equity {current_equity:.2f} < {min_allowed_equity:.2f} "
                f"(limit {max_dd_percent}%)"
            )
        # elif current_equity < min_allowed_equity * 1.1:  # optional 10% warning buffer
        #     violations.append(
        #         f"TOTAL_DRAWDOWN_WARNING: Equity {current_equity:.2f} close to limit {min_allowed_equity:.2f}"
        #     )
        # print("DONE CHECKING TOTAL DD")
        return violations

    
    def _check_profit(self, account: AccountData, challenge: PropFirmChallenge) -> bool:
        """Check if account has reached the profit target."""
        # logger.info("CHECKING PROFIT")
        current_profit = account.profit
        if account.step == 2:
            target_profit_amount = (challenge.phase_2_profit_target_percent / Decimal(100)) * challenge.account_size
        else:
            target_profit_amount = (challenge.profit_target_percent / Decimal(100)) * challenge.account_size
        logger.info(f"CURRENT PROFIT-{current_profit} TARGET PROFIT-{target_profit_amount}")

        # Check if profit target is reached
        return current_profit >= target_profit_amount