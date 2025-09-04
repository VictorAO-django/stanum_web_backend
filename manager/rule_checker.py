import MT5Manager
from trading.models import MT5Deal, MT5Account, MT5AccountHistory, MT5User, MT5Order, MT5Position, MT5OrderHistory, RuleViolationLog
from challenge.models import PropFirmChallenge
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Q, Count, Sum
from django.utils import timezone
import logging
from typing import List

logger = logging.getLogger(__name__)

class RuleChecker:
    """Database-driven rule checker that persists across bridge restarts"""
    
    def get_challenge_config(self, mt5_login):
        """Get challenge config for an MT5 account"""
        try:
            challenge_account = MT5User.objects.get(
                login=str(mt5_login)
            )
            return challenge_account.challenge
        except MT5User.DoesNotExist:
            print(f"No challenge found for MT5 account {mt5_login}")
            return None
    
    def check_position_rules(self, position: MT5Manager.MTPosition, account: MT5Manager.MTAccount) -> List[str]:
        """Check rules for a new deal"""
        print("Analysing position", position.Login)
        violations = []
        challenge = self.get_challenge_config(position.Login)
        
        if not challenge:
            return violations
        
        user = MT5User.objects.get(login=position.Login)

        # 1. Check HFT (High Frequency Trading)
        violations.extend(self._check_hft(position, challenge))
        
        # 2. Check risk per trade
        violations.extend(self._check_risk_per_trade(position, challenge, user, account))
        
        # 3 Check Overall Risk limit
        violations.extend(self._check_overall_risk_limit(position, challenge, user, account))

        # 3. Check symbol position limit (max 2 per symbol)
        violations.extend(self._check_symbol_limit(position, challenge))
        
        # 4. Check for grid/martingale patterns
        violations.extend(self._check_prohibited_strategies(position, challenge))
        
        return violations
    
    def check_account_rules(self, account: MT5Account) -> List[str]:
        """Check account-level rules (drawdown, daily loss)"""
        violations = []
        challenge = self.get_challenge_config(account.login)
        
        if not challenge:
            return violations
            
        # 1. Check drawdown limits
        violations.extend(self._check_drawdown(account, challenge))
        
        # 2. Check daily loss limits
        # violations.extend(self._check_daily_loss(account, challenge))
        
        return violations
    
    def _check_hft(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
        """Check for High Frequency Trading using database queries"""
        violations = []
        
        # Count trades in last minute from database
        one_minute_ago = timezone.now() - timedelta(minutes=1)
        one_hour_ago = timezone.now() - timedelta(hours=1)
        
        recent_trades_count_1_min = MT5Position.objects.filter(login=position.Login, created_at__gte=one_minute_ago).count()
        recent_trades_count_1_hr = MT5Position.objects.filter(login=position.Login, created_at__gte=one_hour_ago).count()
        
        if recent_trades_count_1_min > challenge.max_trades_per_minute:
            violations.append(f"HFT_VIOLATION: {recent_trades_count_1_min} trades in 1 minute (limit: {challenge.max_trades_per_minute})")
        
        if recent_trades_count_1_hr > challenge.max_trades_per_hour:
            violations.append(f"HFT_VIOLATION: {recent_trades_count_1_hr} trades in 1 hour (limit: {challenge.max_trades_per_hour})")

        return violations
    

    def _check_risk_per_trade(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge, user: MT5User, account: MT5Manager.MTAccount) -> List[str]:
        violations = []

        if account.Equity <= 0:
            return violations

        # Get position details
        volume = abs(float(position.Volume))
        price_open = float(position.PriceOpen)
        equity = float(account.Equity)
        
        # Calculate actual risk (you need stop loss for this)
        if hasattr(position, 'PriceSL') and position.PriceSL > 0:
            stop_loss = float(position.PriceSL)
            
            # Calculate risk per unit
            risk_per_unit = abs(price_open - stop_loss)
            
            # Calculate total risk amount
            pip_value = volume * risk_per_unit  # This may need adjustment based on instrument
            risk_amount = pip_value
            
            # Calculate risk as percentage of equity
            risk_percent = (risk_amount / equity) * 100
            
            print(f"DEBUG - Risk Amount: {risk_amount}, Risk Percent: {risk_percent}%")
            
            max_risk = challenge.max_risk_per_trade_percent
            
            if risk_percent > max_risk:
                violations.append(f"RISK_EXCEEDED: {risk_percent:.2f}% risk (max: {max_risk}%)")
        else:
            # If no stop loss, you might want to flag this as unlimited risk
            violations.append("NO_STOP_LOSS: Position has unlimited risk")
            
        return violations
    
    
    def _check_overall_risk_limit(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge, user: MT5User, account: MT5Manager.MTAccount) -> List[str]:
        """Check overall risk across all open positions"""
        violations = []
        
        if account.Equity <= 0:
            return violations
        
        # Get all current open positions for this login
        all_positions = MT5Position.objects.filter(login=position.Login, closed=False)
        
        total_risk_amount = 0
        positions_without_stops = 0
        
        for pos in all_positions:
            volume = abs(float(pos.volume))
            price_open = float(pos.price_open)
            
            # Calculate actual risk based on stop loss
            if hasattr(pos, 'price_sl') and pos.price_sl and float(pos.price_sl) > 0:
                stop_loss = float(pos.price_sl)
                
                # Risk per unit (distance to stop loss)
                risk_per_unit = abs(price_open - stop_loss)
                
                # Total risk for this position
                position_risk = volume * risk_per_unit  # May need adjustment for different instruments
                total_risk_amount += position_risk
                
            else:
                # Position without stop loss = unlimited risk
                positions_without_stops += 1
        
        # Calculate total risk percentage
        total_risk_percent = (total_risk_amount / float(account.Equity)) * 100
        
        print(f"DEBUG - Total Risk Amount: {total_risk_amount}, Total Risk %: {total_risk_percent}%")
        
        max_overall_risk = challenge.overall_risk_limit_percent
        
        if total_risk_percent > max_overall_risk:
            violations.append(f"OVERALL_RISK_EXCEEDED: {total_risk_percent:.2f}% total risk (max: {max_overall_risk}%)")
        
        if positions_without_stops > 0:
            violations.append(f"POSITIONS_WITHOUT_STOPS: {positions_without_stops} positions have unlimited risk")
        
        return violations
    
    def _check_symbol_limit(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
        """Check max 2 positions per symbol using database"""
        violations = []
        
        # Count current open positions for this symbol
        current_positions = MT5Position.objects.filter(
            login=position.Login,
            symbol=position.Symbol,
            closed=False
        ).count()
        
        max_positions_per_symbol = challenge.max_orders_per_symbol
        
        if current_positions > max_positions_per_symbol:
            violations.append(f"SYMBOL_LIMIT: {current_positions} positions on {position.Symbol} (max: {max_positions_per_symbol})")
                
        return violations
    
    def _check_prohibited_strategies(self, position: MT5Manager.MTPosition, challenge: PropFirmChallenge) -> List[str]:
        """Basic grid/martingale/hedging detection using database queries"""
        violations = []
        
        # Get recent positions for this login (last 24 hours)
        positions = MT5Position.objects.filter(
            login=position.Login,
            closed=False
        ).order_by('-created_at')
        
        if not challenge.grid_trading_allowed:
            if positions.count() >= 3:
                positions_list = list(positions)
                
                # Simple grid detection: 3+ trades with same volume
                volumes = [float(d.volume) for d in positions_list]
                if len(set(volumes)) == 1:  # All same volume
                    violations.append(f"GRID_DETECTED: Equal volumes ({volumes[0]}) on {position.Symbol}")
        
        if not challenge.martingale_allowed:
            # Simple martingale detection: check if volume doubled after loss
            if positions.count() >= 2:
                positions_list = list(positions)
                previous_position = positions_list[1]  # Second most recent
                
                if (float(previous_position.profit) < 0 and  # Previous trade was loss
                    float(position.Volume) >= float(previous_position.volume) * 1.8):  # Current volume ~doubled
                    violations.append(f"MARTINGALE_DETECTED: Volume increase after loss on {position.Symbol}")
        
        if not challenge.hedging_within_account_allowed:
            # Hedging detection: Check for opposing positions on same symbol
            current_positions = MT5Position.objects.filter(
                login=position.Login,
                symbol=position.Symbol
            ).exclude(position_id=position.Position)  # Exclude current position
            
            for existing_pos in current_positions:
                # Check if positions are opposing (different action types)
                if existing_pos.action != position.Action:  # 0=BUY, 1=SELL
                    violations.append(f"HEDGING_DETECTED: Opposing positions on {position.Symbol} - Current: {'BUY' if position.Action == 0 else 'SELL'}, Existing: {'BUY' if existing_pos.action == 0 else 'SELL'}")
                    break  # Only report once per symbol
                    
        return violations
    
    def _check_drawdown(self, account: MT5Account, challenge: PropFirmChallenge) -> List[str]:
        """Check drawdown limits using database for equity peak"""
        violations = []
        
        # Get highest equity from account history or use initial balance
        # You might want to track equity peaks in a separate field or table
        # For now, using max of current equity and initial balance
        equity_peak = max(float(account.equity), float(challenge.account_size))
            
        # Calculate trailing drawdown
        current_equity = float(account.equity)
        current_dd_percent = ((equity_peak - current_equity) / equity_peak) * 100
        
        max_dd = float(challenge.max_total_loss_percent)
        
        if current_dd_percent > max_dd:
            violations.append(f"DRAWDOWN_EXCEEDED: {current_dd_percent:.2f}% (max: {max_dd}%)")
        elif current_dd_percent > max_dd * 0.8:  # 80% warning threshold
            violations.append(f"DRAWDOWN_WARNING: {current_dd_percent:.2f}% (limit: {max_dd}%)")
            
        return violations
    
    def _check_daily_loss(self, account: MT5Account, challenge: PropFirmChallenge) -> List[str]:
        """Check daily loss limits using database"""
        violations = []
        
        # Get today's starting equity (you'll need to implement daily equity tracking)
        # This is a simplified version - you might want a separate DailyEquity model
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        try:
            # Get the first account record from today or use challenge starting balance
            today_start_equity = MT5AccountHistory.objects.filter(
                login=account.login,
                updated_at__gte=today_start
            ).order_by('updated_at').first()
            
            if today_start_equity:
                starting_equity = float(today_start_equity.equity)
            else:
                starting_equity = float(challenge.account_size)
                
        except Exception:
            starting_equity = float(challenge.account_size)
        
        current_equity = float(account.equity)
        daily_loss_percent = ((starting_equity - current_equity) / starting_equity) * 100
        
        max_daily_loss = float(challenge.max_daily_loss_percent)
        
        if daily_loss_percent > max_daily_loss:
            violations.append(f"DAILY_LOSS_EXCEEDED: {daily_loss_percent:.2f}% (max: {max_daily_loss}%)")
        elif daily_loss_percent > max_daily_loss * 0.8:  # 80% warning
            violations.append(f"DAILY_LOSS_WARNING: {daily_loss_percent:.2f}% (limit: {max_daily_loss}%)")
            
        return violations