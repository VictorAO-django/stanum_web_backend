import MT5Manager, traceback
from datetime import date
from django.utils.timezone import now
from typing import List, Dict
from trading.models import *
from account.models import Notification
from trading.tasks import *

from .InMemoryData import *
from .InMemoryRuleChecker import *

from .logging_config import get_prop_logger
logger = get_prop_logger('monitoring')

class InMemoryPropMonitoring:
    def __init__(self, bridge):
        self.bridge = bridge
        self.rule_checker = InMemoryRuleChecker()

        self.local_accounts: Dict[int, AccountData] = {}
        self.positions: Dict[int, List[PositionData]] = {}
        self.account_challenge: Dict[int, PropFirmChallenge] = {}

        self.symbol:Dict[str, MT5Manager.MTTick] = {}

        self.daily_drawdowns: Dict[int, Dict[date, DailyDrawdownData]] = {}
        self.total_drawdown: Dict[int, AccountTotalDrawdownData] = {}

        self._load_local_accounts()
        self._load_positions()

        self.count = 0

        logger.info("InMemoryMonitor Initialized")

    def _load_local_accounts(self):
        for acc in MT5Account.objects.filter(active=True):
            self.add_account(acc)
    
    def remove_account(self, login):
        self.cleanup_completed_account(login)
        logger.info(f"Account Removed {login}")

    def add_account(self, acc:MT5Account):
        acc_state =  AccountData(
            login=acc.login, currency_digits=acc.currency_digits, balance=acc.balance, credit=acc.credit, margin=acc.margin,
            prev_margin=acc.prev_margin, margin_free=acc.margin_free, prev_margin_free=acc.prev_margin_free, margin_level=acc.margin_level,
            margin_leverage=acc.margin_leverage, margin_initial=acc.margin_initial, margin_maintenance=acc.margin_maintenance,
            profit=acc.profit, storage=acc.storage, commission=acc.commission, floating=acc.floating, equity=acc.equity, prev_equity=acc.prev_equity,
            so_activation=acc.so_activation, so_time=acc.so_time, so_level=acc.so_level, so_equity=acc.so_equity, so_margin=acc.so_margin,
            blocked_commission=acc.blocked_commission, blocked_profit=acc.blocked_profit, assets=acc.assets, liabilities=acc.liabilities,
            active=acc.active, created_at=acc.created_at, updated_at=acc.updated_at, step=acc.step
        )
        self.local_accounts[acc.login] = acc_state
        self.account_challenge[acc.login] = acc.mt5_user.challenge
        logger.info(f"Added Account {acc.login}")
    
    def update_account(self, acc: MT5Account):
        try:
            if acc.login not in self.local_accounts:
                # Option 1: silently add it
                self.add_account(acc)
                return

            updated = AccountData(
                login=acc.login, currency_digits=acc.currency_digits, balance=acc.balance, credit=acc.credit, margin=acc.margin,
                prev_margin=acc.prev_margin, margin_free=acc.margin_free, prev_margin_free=acc.prev_margin_free, margin_level=acc.margin_level,
                margin_leverage=acc.margin_leverage, margin_initial=acc.margin_initial, margin_maintenance=acc.margin_maintenance,
                profit=acc.profit, storage=acc.storage, commission=acc.commission, floating=acc.floating, equity=acc.equity, prev_equity=acc.prev_equity,
                so_activation=acc.so_activation, so_time=acc.so_time, so_level=acc.so_level, so_equity=acc.so_equity, so_margin=acc.so_margin,
                blocked_commission=acc.blocked_commission, blocked_profit=acc.blocked_profit, assets=acc.assets, liabilities=acc.liabilities,
                active=acc.active, created_at=acc.created_at, updated_at=acc.updated_at, step=acc.step
            )
            self.local_accounts[acc.login] = updated
            self.account_challenge[acc.login] = acc.mt5_user.challenge
            logger.info(f"Updated Account {acc.login}")

        except Exception as err:
            logger.debug(f"Error while updating Account {str(err)}")
    
    def _load_positions(self):
        positions = MT5Position.objects.filter(closed=False)
        for pos in positions:
            pos_state = PositionData(
                position_id=pos.position_id, login=pos.login, symbol=pos.symbol, comment=pos.comment,
                price_open=pos.price_open, price_current=pos.price_current, price_sl=pos.price_sl,
                price_tp=pos.price_tp, price_gateway=pos.price_gateway, volume=pos.volume, volume_ext=pos.volume_ext,
                volume_gateway_ext=pos.volume_gateway_ext, profit=pos.profit, storage=pos.storage, contract_size=pos.contract_size,
                rate_margin=pos.rate_margin, rate_profit=pos.rate_profit, expert_id=pos.expert_id, expert_position_id=pos.expert_position_id,
                dealer=pos.dealer, external_id=pos.external_id, time_create=pos.time_create, time_update=pos.time_update,
                action=pos.action, reason=pos.reason, digits=pos.digits, digits_currency=pos.digits_currency, obsolete_value=pos.obsolete_value
            )
            self.positions.setdefault(pos.login, []).append(pos_state)
        logger.info(f"Positions Loaded {len(positions)}")
    
    def add_position(self, pos:MT5Position):
        try:
            pos_state = PositionData(
                position_id=pos.position_id, login=pos.login, symbol=pos.symbol, comment=pos.comment,
                price_open=pos.price_open, price_current=pos.price_current, price_sl=pos.price_sl,
                price_tp=pos.price_tp, price_gateway=pos.price_gateway, volume=pos.volume, volume_ext=pos.volume_ext,
                volume_gateway_ext=pos.volume_gateway_ext, profit=pos.profit, storage=pos.storage, contract_size=pos.contract_size,
                rate_margin=pos.rate_margin, rate_profit=pos.rate_profit, expert_id=pos.expert_id, expert_position_id=pos.expert_position_id,
                dealer=pos.dealer, external_id=pos.external_id, time_create=pos.time_create, time_update=pos.time_update,
                action=pos.action, reason=pos.reason, digits=pos.digits, digits_currency=pos.digits_currency, obsolete_value=pos.obsolete_value
            )
            self.positions.setdefault(pos.login, []).append(pos_state)
            logger.info(f"Position Addedd {pos.login}")
            # self._check_trading_rules(pos.login)

        except Exception as err:
            logger.debug(f"Error while updating position {str(err)}")

    def update_position(self, pos: MT5Position):
        try:
            pos_entry = self.positions.get(pos.login, None)
            if not pos_entry:
                return  # nothing to update

            for i, existing in enumerate(pos_entry):
                if existing.position_id == pos.position_id:
                    # overwrite with fresh data
                    updated = PositionData(
                        position_id=pos.position_id, login=pos.login, symbol=pos.symbol, comment=pos.comment,
                        price_open=pos.price_open, price_current=pos.price_current, price_sl=pos.price_sl,
                        price_tp=pos.price_tp, price_gateway=pos.price_gateway, volume=pos.volume, volume_ext=pos.volume_ext,
                        volume_gateway_ext=pos.volume_gateway_ext, profit=pos.profit, storage=pos.storage, contract_size=pos.contract_size,
                        rate_margin=pos.rate_margin, rate_profit=pos.rate_profit, expert_id=pos.expert_id, expert_position_id=pos.expert_position_id,
                        dealer=pos.dealer, external_id=pos.external_id, time_create=pos.time_create, time_update=pos.time_update,
                        action=pos.action, reason=pos.reason, digits=pos.digits, digits_currency=pos.digits_currency, obsolete_value=pos.obsolete_value
                    )
                    pos_entry[i] = updated
                    break
            logger.info(f"Position Updated {pos.login}")
        except Exception as err:
            logger.debug(f"Error while updating position {str(err)}")

    def remove_position(self, pos: MT5Position):
        try:
            pos_entry = self.positions.get(pos.login, None)
            if pos_entry:
                for i in pos_entry:
                    if i.position_id == pos.position_id:
                        pos_entry.remove(i) #Remove Position
                        break   # stop after removing
            logger.info(f"Position Removed {pos.login}")
        except Exception as err:
            logger.debug(f"Error while removing position {str(err)}")
    
    def _clear_positions(self, login):
        self.positions[login] = []
    
    def cleanup_completed_account(self, login: int):
        """Remove all data for completed/failed accounts"""
        self.local_accounts.pop(login, None)
        self.positions.pop(login, None) 
        self.account_challenge.pop(login, None)
        self.daily_drawdowns.pop(login, None)
        self.total_drawdown.pop(login, None)
        logger.info(f"Cleaned up completed account {login}")
                
    def _check_trading_rules(self, login):
        account = self.local_accounts.get(login)
        violations = self.rule_checker.check_position_rules(account)
        # Handle position violations through bridge
        if violations and self.bridge:
            # self.bridge.handle_violation(login, violations, "POSITION")
            logger.info(f"Violations detected ({violations})")
        elif violations:
            # Fallback logging if bridge not available
            logger.debug(f"Violations detected for {login} but no bridge available: {violations}")

    def _move_to_step_2(self, login, challenge:PropFirmChallenge):
        try:
            acc = self.local_accounts.get(login)
            acc.step = 2

            mt5_account = MT5Account.objects.get(login=login)
            mt5_account.step = 2
            mt5_account.phase_2_start_date = now()
            mt5_account.save()

            # Reset tracking for new phase
            self._reset_phase_tracking(login)
            self.bridge._close_all_positions(login)
            self.bridge.return_account_balance(login, challenge.account_size)
            self._send_phase_1_success_notification(mt5_account.mt5_user, challenge)

            logger.info(f"Account {login} successfully moved to Phase 2")
        except Exception as err:
            logger.debug(f"Error processing Phase 1 pass for {login}: {str(err)}")

    def _challenge_passed(self,acc:AccountData,challenge:PropFirmChallenge):
        """Handle complete challenge success - eligible for funded account"""
        try:
            mt5_account = MT5Account.objects.get(login=acc.login)
            mt5_account.challenge_completed = True
            mt5_account.challenge_completion_date = now()
            mt5_account.is_funded_eligible = True
            mt5_account.save()

            mt5_user = mt5_account.mt5_user
            mt5_user.account_status = 'challenge_passed'
            mt5_user.save()

            if challenge.challenge_type == 'one_step':
                self._send_challenge_success_notification(mt5_user, challenge)
            else:
                self._send_phase_2_success_notification(mt5_user, challenge)

            self.bridge.disable_challenge_account_trading(acc.login)
            self.cleanup_completed_account(acc.login)
            logger.info(f"Challenge PASSED for account {acc.login}")

        except Exception as err:
            logger.debug(f"Error processing challenge pass for {acc.login}: {str(err)}")

    def _challenge_failed(self, login: int, reasons:List[str], challenge:PropFirmChallenge):
        """Handle complete challenge failure"""
        try:
            mt5_account = MT5Account.objects.get(login=login)
            mt5_account.challenge_failed = True
            mt5_account.challenge_failure_date = now()
            mt5_account.active = False
            mt5_account.failure_reason = reasons
            mt5_account.save()

            mt5_user = mt5_account.mt5_user
            mt5_user.account_status = 'disabled'
            mt5_user.save()

            #CLEAR IN MEMORY POSITION
            self._clear_positions(login)
            #DISAVLE ACCOUNT AND CLOSE POSITIONS ON MT5
            self.bridge.disable_challenge_account_trading(login)
            #SEND NOTIFICATION ALERT
            self._send_challenge_failure_notification(mt5_user, challenge, reasons)

            logger.info(f"Successfully processed challenge failure {login}")
            self.cleanup_completed_account(login)

        except Exception as err:
            logger.debug(f"Error processing challenge failure for {login}: {str(err)}")

    def _reset_phase_tracking(self, login):
        """Reset tracking data for new phase"""
        account = self.local_accounts.get(login)
        
        # Clear daily drawdown tracking
        if login in self.daily_drawdowns:
            self.daily_drawdowns[login].clear()
        
        # Only reset total drawdown if organization rules specifically allow it
        if login in self.total_drawdown:
            # Set new peak to current equity (fresh start for Phase 2)
            self.total_drawdown[login].equity_peak = account.equity
            self.total_drawdown[login].equity_low = account.equity
            self.total_drawdown[login].drawdown_percent = Decimal("0")
        
        if login in self.positions:
            self.positions[login] = []
        
        logger.info(f"Phase 2: Fresh total drawdown tracking started at {account.equity}")
    
    def _clear_drawdowns(self, login: int):
        self.total_drawdown.pop(login, None)       # remove total dd for this account
        self.daily_drawdowns.pop(login, None)      # remove all daily dd for this account

    def OnTick(self, symbol: str, tick:MT5Manager.MTTick):
        try:
            self.symbol[symbol] = tick
            accounts =  self.get_accounts_with_symbol(symbol)
            # print(f"ACCOUNTS WITH SYMBOL({symbol})", len(accounts))
            for acc in accounts:
                self.update_account_equity(acc.login)
                dd = self.update_drawdown(acc.login)
                total_dd = self.update_total_drawdown(acc.login)

                challenge = self.account_challenge.get(acc.login)
                broken_rules = self.rule_checker.check_account_rules(acc, challenge, dd, total_dd) 

                if len(broken_rules) == 0:
                    # Check if minimum days requirement met
                    if not self.rule_checker._check_min_days(acc, challenge):
                        # logger.info(f"NO ACCOUNT VIOLATIONS BUT MIN DAYS NOT REACHED YET {acc.login}")
                        return False

                    # Check if profit target met
                    if self.rule_checker._check_profit(acc, challenge):
                        # Both conditions met - determine next action based on phase
                        if (challenge.challenge_type == 'two_step') and (acc.step == 1):
                            # Move to Phase 2
                            self._move_to_step_2(acc.login, challenge)
                            return True
                        else:
                            # Challenge fully completed
                            self._challenge_passed(acc, challenge)
                            # Now clear drawdowns since challenge is fully done
                            self._clear_drawdowns(acc.login)
                            return True
                    # logger.info(f"NO ACCOUNT VIOLATIONS BUT TARGET PROFIT NOT YET MADE {acc.login}")
                    return False
                else:
                    self._handle_account_rules_violation(acc.login, broken_rules)
                    self._challenge_failed(acc.login, broken_rules, challenge)

        except Exception as err:
            logger.error("Error processing OnTick", exc_info=True)
            traceback.print_exc()
    
    def get_accounts_with_symbol(self, symbol: str) -> List[AccountData]:
        accounts = []
        for login, account in self.local_accounts.items():
            pos_list = self.positions.get(login, [])
            for pos in pos_list:
                if pos.symbol == symbol:
                    accounts.append(account)
                    break  # no need to check more positions for this login
        return accounts

    def update_account_equity(self, login: int):
        try:
            """Recalculate account equity, margin, free margin for a given account."""
            positions = self.positions.get(login, [])
            account = self.local_accounts.get(login, None)
            if not account:
                return  # no account to update

            balance = account.balance
            profit = Decimal("0")
            margin = Decimal("0")
            leverage = Decimal(account.margin_leverage or 100)

            # logger.info(f"Starting calculation: Balance-{balance} Positions-{len(positions)}")

            for pos in positions:
                price = self.symbol.get(pos.symbol)
                # print("SYMBOL", price.ask, price.bid)
                if not price:
                    continue

                current_bid = Decimal(str(price.bid))
                current_ask = Decimal(str(price.ask))
                volume_in_lots = Decimal(pos.volume / 10000)
                contract_size = Decimal(pos.contract_size or 100000)

                if pos.action == 0:  # BUY
                    pnl = (current_bid - Decimal(pos.price_open)) * volume_in_lots * contract_size
                    margin_price = current_ask
                else:  # SELL
                    pnl = (pos.price_open - current_ask) * volume_in_lots * contract_size
                    margin_price = current_bid

                profit += pnl
                position_margin = (volume_in_lots * contract_size * margin_price) / leverage
                margin += position_margin

                # update position state
                pos.profit = float(pnl)
                # pos.time_update = int(time.time())

            equity = Decimal(balance) + profit
            free_margin = equity - margin

            # logger.info(f"Final calculation: Total Profit-{profit} Total Margin-{margin} Equity-{equity} Free Margin-{free_margin}")

            # update account state
            account.prev_equity = account.equity
            account.equity = equity
            account.prev_margin = account.margin
            account.margin = margin
            account.prev_margin_free = account.margin_free
            account.margin_free = free_margin
            account.profit = profit

            return account

        except Exception as err:
            logger.debug(f"Error updating account equity: {str(err)}")
            traceback.print_exc()

    def update_drawdown(self, login: int):
        try:
            # print("Updating Drawdown")
            today = now().date()
            account = self.local_accounts.get(login)
            if not account:
                return None  # no account to update

            # Ensure login entry exists
            if login not in self.daily_drawdowns:
                self.daily_drawdowns[login] = {}

            dd = self.daily_drawdowns[login].get(today)
            if not dd:
                state = DailyDrawdownData(
                    login=login,
                    date=today,
                    equity_high=account.equity,
                    equity_low=account.equity,
                    drawdown_percent=Decimal("0"),
                )
                dd = self.daily_drawdowns[login][today] = state

            # print('DD', dd)
            updated = False

            # Update highs and lows
            if account.equity > dd.equity_high:
                dd.equity_high = account.equity
                updated = True

            if dd.equity_low == 0 or account.equity < dd.equity_low:
                dd.equity_low = account.equity
                updated = True

            # Recalculate drawdown %
            if dd.equity_high > 0:
                dd.drawdown_percent = (
                    (dd.equity_high - dd.equity_low) / dd.equity_high * 100
                )
                updated = True
            # logger.info(f'Final level: HIGH-{dd.equity_high} LOW-{dd.equity_low} DRAWDOWN_PERCENT-{dd.drawdown_percent}' )
            return dd

        except Exception as err:
            logger.debug(f"Error updating account drawdown: {str(err)}")
            traceback.print_exc()
    
    def update_total_drawdown(self, login: int):
        """
        Update or create the total drawdown record for an account.
        Tracks all-time equity peak and current equity lows.
        """
        try:
            # print("STARTING TOTAL DRAWDOWN", login)
            account = self.local_accounts.get(login)
            if not account:
                return None  # no account to update
            
            challenge = self.account_challenge.get(login)
            if not challenge:
                return None  # no challenge info available

            td = self.total_drawdown.get(login, None)
            if not td:
                td = self.total_drawdown[login] = AccountTotalDrawdownData(
                    login=login,
                    equity_peak=challenge.account_size,
                    equity_low=account.equity,
                    drawdown_percent=Decimal("0"),
                )

            # Update peak if current equity is higher
            if account.equity > td.equity_peak:
                td.equity_peak = account.equity
                td.equity_low = account.equity  # reset low after new peak
            else:
                # Update equity low if lower
                if td.equity_low == 0 or account.equity < td.equity_low:
                    td.equity_low = account.equity

            # Recalculate drawdown %
            if td.equity_peak > 0:
                td.drawdown_percent = ((Decimal(td.equity_peak) - Decimal(td.equity_low)) / Decimal(td.equity_peak)) * 100

            # print(f"FINAL: PEAK-{td.equity_peak} LOW-{td.equity_low}")
            return td
        
        except Exception as err:
            logger.debug(f"Error updating account total drawdown: {str(err)}")
            traceback.print_exc()

    def _handle_account_rules_violation(self, login: int, violations: List[str]):
        """Handle rule violations - warnings or account restrictions"""
        try:
            for violation in violations:
                # Log violation
                RuleViolationLog.objects.create(
                    login=login,
                    violation_type="RULES_VIOLATION",
                    violations=violation,
                    message='critical',
                    timestamp=now(),
                    auto_closed=True
                )
            logger.info(f"Violations logged for {login}: {violations}")
            
        except Exception as e:
            logger.debug(f"Error logging violations for {login}: {e}")
        

    def _send_phase_1_success_notification(self, user: MT5User, challenge: PropFirmChallenge):
        try:
            result = send_phase_1_success_task.delay(user.login, challenge.id)
        except Exception as err:
            logger.debug(f"Could not send phase q success notification {user.login} - {str(err)}")

    def _send_phase_2_success_notification(self, user: MT5User, challenge: PropFirmChallenge):
        try:
            result = send_phase_2_success_task.delay(user.login, challenge.id)
        except Exception as err:
            logger.debug(f"Could not send phase q success notification {user.login} - {str(err)}")

    def _send_challenge_success_notification(self, user: MT5User, challenge: PropFirmChallenge):
        try:
            result = send_challenge_success_mail_task.delay(user.login, challenge.id)
        except Exception as err:
            logger.debug(f"Could not send challenge success notification {user.login} - {str(err)}")


    def _send_challenge_failure_notification(self, user: MT5User, challenge: PropFirmChallenge, reasons: List[str]):
        try:
            result = send_challenge_failed_mail_task.delay(user.login, challenge.id, reasons)
        except Exception as err:
            logger.debug(f"Could not send challenge failure notification {user.login} - {str(err)}")


    def cleanup_old_daily_drawdowns(self, days_to_keep: int = 30):
        """Remove daily drawdown data older than specified days"""
        cutoff_date = (now() - timedelta(days=days_to_keep)).date()
        
        for login in self.daily_drawdowns:
            dates_to_remove = [date for date in self.daily_drawdowns[login] 
                            if date < cutoff_date]
            for date in dates_to_remove:
                del self.daily_drawdowns[login][date]


    def cleanup_unused_symbols(self):
        """Remove tick data for symbols not in any active positions"""
        used_symbols = set()
        for positions in self.positions.values():
            for pos in positions:
                used_symbols.add(pos.symbol)
        
        symbols_to_remove = [symbol for symbol in self.symbol 
                            if symbol not in used_symbols]
        for symbol in symbols_to_remove:
            del self.symbol[symbol]
        
        if symbols_to_remove:
            logger.info(f"Cleaned up {len(symbols_to_remove)} unused symbols")








    ###############################################################################################################################
    ################# API USAGE
    ###############################################################################################################################
    def account_stat(self, login: int):
        data = {
            'balance': 0, 'equity': 0,
            'avg_winning_trade': 0, 'avg_losing_trade': 0,
            'profit_target': 0, 'profit': 0,
            'win_ratio': 0, 'profit_factor': 0
        }

        acc = self.local_accounts.get(login)
        if not acc:
            return data

        winning = Decimal(0)
        losing = Decimal(0)
        winning_count = 0
        losing_count = 0

        positions = self.positions.get(login, [])
        for pos in positions:
            if pos.profit > 0:
                winning += pos.profit
                winning_count += 1
            elif pos.profit < 0:
                losing += pos.profit
                losing_count += 1

        # Challenge info
        challenge = self.account_challenge.get(login)
        profit_target = Decimal(0)
        if challenge:
            profit_target = (challenge.profit_target_percent / Decimal(100)) * challenge.account_size

        # Win ratio
        win_ratio = (winning_count / len(positions) * 100) if positions else 0

        # Profit factor
        if losing_count == 0 and winning_count > 0:
            profit_factor = float('inf')
        elif losing_count == 0:
            profit_factor = 0
        else:
            profit_factor = winning / abs(losing)

        data.update({
            'balance': acc.balance,
            'equity': acc.equity,
            'avg_winning_trade': (winning / winning_count) if winning_count > 0 else 0,
            'avg_losing_trade': (losing / losing_count) if losing_count > 0 else 0,
            'profit_target': profit_target,
            'profit': acc.profit,
            'win_ratio': win_ratio,
            'profit_factor': profit_factor,
        })

        return data