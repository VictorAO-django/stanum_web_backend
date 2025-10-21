import MT5Manager, time, traceback, json
from datetime import date
from datetime import time as dtime
from django.utils.timezone import now
from typing import List, Dict, Tuple, Union, Set
from stanum_web.tasks import *
from asgiref.sync import async_to_sync
from sub_manager.InMemoryData import *
from sub_manager.InMemoryRuleChecker import *
from sub_manager.logging_config import get_prop_logger
from sub_manager.producer import redis_client
from .producer import p
from .transformer import *

from confluent_kafka import Consumer, Producer
from .USDCurrencyConverter import USDCurrencyConverter

logger = get_prop_logger('monitoring')


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

class InMemoryPropMonitoring:
    def __init__(self):
        # self.bridge = bridge
        self.rule_checker = InMemoryRuleChecker()
        self.converter = USDCurrencyConverter()

        self.local_accounts: Dict[int, AccountData] = {}
        self.positions: Dict[int, List[PositionData]] = {}
        self.deals: Dict[int, List[DealData]] = {}
        self.account_challenge: Dict[int, PropFirmChallengeData] = {}
        self.account_competition: Dict[int, CompetitionData] = {}

        self.symbol:Dict[str, TickData] = {}

        self.daily_drawdowns: Dict[int, Dict[date, DailyDrawdownData]] = {}
        self.total_drawdown: Dict[int, AccountTotalDrawdownData] = {}
        self.account_watermarks: Dict[int, AccountWatermarksData] = {}

        # --- Trackers ---
        # login -> set of active account rule types (for drawdowns etc.)
        self.active_account_violations: Dict[int, Set[str]] = {}
        # login -> set of active trade rule types (GRID, HFT, MARTINGALE)
        self.active_trade_violations: Dict[int, Set[str]] = {}
        # login -> {rule_type: last_trigger_timestamp}
        self.last_trade_violation_time: Dict[int, Dict[str, float]] = {}
        # login -> {rule_type: count}
        self.violation_counts: Dict[int, Dict[str, int]] = {}
        
        # --- Configurable thresholds ---
        self.trade_violation_cooldown = 60        # seconds between repeated same alerts
        self.account_violation_resolution_delay = 10  # seconds before marking cleared

        self.trade_violation_cooldown=900 #15 minute
        self.account_violation_cooldown=3600 #1 hour

        self.count = 0
        self.last_update_time = {}
        self.last_broadcast_time = {}
        self.lock_account: Set[int] = set()

        logger.info("InMemoryMonitor Initialized")
    
    def remove_account(self, login):
        self.cleanup_completed_account(login)
        logger.info(f"Account Removed {login}")
    
    def update_account(self, acc: AccountData):
        try:
            self.local_accounts[acc.login] = acc
            logger.info(f"Updated Account {acc.login}")
            challenge = self.account_challenge.get(acc.login)
            if not challenge:
                return
            
            # Check if profit target met
            if self.rule_checker._check_profit(acc, challenge):
                self.lock_account.add(acc.login)
                # Both conditions met - determine next action based on phase
                if (challenge.challenge_type == 'two_step') and (acc.step == 1):
                    # Move to Phase 2
                    self._move_to_step_2(acc.login, challenge)
                    print("Reached here 1")

                else:
                    # Challenge fully completed
                    self._challenge_passed(acc, challenge)
                    # Now clear drawdowns since challenge is fully done
                    print("Reached here 2")
                    self._clear_drawdowns(acc.login)

                self.lock_account.discard(acc.login)
            return True
        except Exception as err:
            logger.debug(f"Error while updating Account {str(err)}")
            return False
    
    #############################################################################################################
    ## POSITION
    #############################################################################################################
    def add_position(self, pos:PositionData):
        try:
            self.positions.setdefault(pos.login, []).append(pos)
            #update equity with new position included
            self.update_account_equity(pos.login)

            logger.info(f"Position Addedd {pos.login}")

            positions = self.deals.get(pos.login, [])
            challenge = self.account_challenge.get(pos.login)

            if challenge:
                violations:List[ViolationDict] = []
                violations.extend(self.rule_checker._check_symbol_limit(pos, positions, challenge))
                self._handle_trade_violations(pos.login, pos.symbol, violations)

        except Exception as err:
            logger.debug(f"Error while updating position {str(err)}")

    def update_position(self, pos: PositionData):
        try:
            pos_entry = self.positions.get(pos.login, None)
            if not pos_entry:
                return  # nothing to update

            for i, existing in enumerate(pos_entry):
                if existing.position_id == pos.position_id:
                    # overwrite with fresh data
                    pos_entry[i] = pos
                    break
            logger.info(f"Position Updated {pos.login}")
        except Exception as err:
            logger.debug(f"Error while updating position {str(err)}")

    def remove_position(self, pos: PositionData):
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
        logger.info(f"Position cleared for {login}")

    #############################################################################################################
    ## DEALS
    #############################################################################################################
    def add_deal(self, deal:DealData):
        try:
            self.deals.setdefault(deal.login, []).append(deal)
            logger.info(f"Deal Addedd {deal.login}")

            deals = self.deals.get(deal.login, [])
            challenge = self.account_challenge.get(deal.login)
            if challenge:
                violations:List[ViolationDict] = []
                violations.extend(self.rule_checker._check_hft(deals, challenge))
                violations.extend(self.rule_checker._check_prohibited_strategies(deals, challenge))

                #Handle the Trade Violations
                self._handle_trade_violations(deal.login, deal.symbol, violations)
        except Exception as err:
            logger.debug(f"Error while updating deal {str(err)}")

    def update_deal(self, deal: DealData):
        try:
            deal_entry = self.deals.get(deal.login, None)
            if not deal_entry:
                return  # nothing to update

            for i, existing in enumerate(deal_entry):
                if existing.deal == deal.deal:
                    # overwrite with fresh data
                    deal_entry[i] = deal
                    break
            logger.info(f"Deal Updated {deal.login}")
        except Exception as err:
            logger.debug(f"Error while updating deal {str(err)}")

    def remove_deal(self, deal: DealData):
        try:
            deal_entry = self.deals.get(deal.login, None)
            if deal_entry:
                for i in deal_entry:
                    if i.deal == deal.deal:
                        deal_entry.remove(i) #Remove Position
                        break   # stop after removing
            logger.info(f"Deal Removed {deal.login}")
        except Exception as err:
            logger.debug(f"Error while removing deal {str(err)}")
    
    def _clear_deals(self, login):
        self.deals[login] = []
        logger.info(f"Deals cleared for {login}")

    def _handle_trade_violations(self, login: int, symbol: str, violations: List[ViolationDict]):
        """Handle trade-based violations (GRID, MARTINGALE, HFT) with cooldown and escalation."""
        try:
            now = time.time()
            cooldown = self.trade_violation_cooldown  # 5 minutes

            # Ensure data structures exist for this account
            self.active_trade_violations.setdefault(login, set())
            self.last_trade_violation_time.setdefault(login, {})
            self.violation_counts.setdefault(login, {})

            compiled_violations: List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]] = []

            for violation in violations:
                vtype = violation["type"]
        
                # Get last trigger timestamp
                last_trigger = self.last_trade_violation_time[login].get(vtype, 0)
                elapsed = now - last_trigger

                # Only trigger if violation is new or cooldown expired
                if vtype not in self.active_trade_violations[login] or elapsed >= cooldown:
                    self.active_trade_violations[login].add(vtype)
                    self.last_trade_violation_time[login][vtype] = now

                    # Escalation logic
                    count = self.violation_counts[login].get(vtype, 0) + 1
                    self.violation_counts[login][vtype] = count

                    severity: Literal['warning', 'severe', 'critical'] = (
                        'warning' if count == 1 else 'severe' if count == 2 else 'critical'
                    )

                    compiled_violations.append((violation, severity))

            # Send notifications if new violations compiled
            if compiled_violations:
                trade_rule_violation_alert.delay(login, compiled_violations, symbol)
                logger.info(f"[TRADE VIOLATION] {login}: {compiled_violations}")

        except Exception as e:
            logger.error(f"Error handling trade violations for {login}: {e}")


    def _handle_account_rules_violation(self, login: int, violations: List[ViolationDict]):
        """Handle ongoing account rule violations (drawdown, etc.) without spamming notifications."""
        try:
            now = time.time()
            cooldown = self.account_violation_cooldown  # 1 hour – minimum gap before resending same violation
            compiled_violations: List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]] = []

            # Ensure per-account structures exist
            self.active_account_violations.setdefault(login, set())
            self.last_trade_violation_time.setdefault(login, {})
            self.violation_counts.setdefault(login, {})

            # Get violation types currently active
            current_types = {v["type"] for v in violations}
            previously_active = self.active_account_violations[login]

            # Handle new or re-triggered violations
            for violation in violations:
                vtype = violation["type"]
                last_trigger = self.last_trade_violation_time[login].get(vtype, 0)
                elapsed = now - last_trigger

                if vtype not in previously_active or elapsed >= cooldown:
                    self.active_account_violations[login].add(vtype)
                    self.last_trade_violation_time[login][vtype] = now

                    # Severity can be fixed or escalate with repeated breaches
                    count = self.violation_counts[login].get(vtype, 0) + 1
                    self.violation_counts[login][vtype] = count

                    severity: Literal['warning', 'severe', 'critical'] = (
                        'warning' if count == 1 else 'severe' if count == 2 else 'critical'
                    )

                    compiled_violations.append((violation, severity))

            # Handle cleared conditions (rule no longer violated)
            cleared = previously_active - current_types
            if cleared:
                for vtype in cleared:
                    self.active_account_violations[login].remove(vtype)

            # Send notification only for new/retiggered violations
            if compiled_violations:
                account_rule_violation_log.delay(login, compiled_violations)
                logger.info(f"[ACCOUNT VIOLATION] {login}: {compiled_violations}")

        except Exception as e:
            logger.error(f"Error handling account violations for {login}: {e}")


    def cleanup_completed_account(self, login: int):
        """Remove all data for completed/failed accounts"""
        self.local_accounts.pop(login, None)
        self.positions.pop(login, None) 
        self.deals.pop(login, None) 
        self.account_challenge.pop(login, None)
        self.daily_drawdowns.pop(login, None)
        self.total_drawdown.pop(login, None)
        self.violation_counts.pop(login, None)
        logger.info(f"Cleaned up completed account {login}")

    def _move_to_step_2(self, login, challenge:PropFirmChallengeData):
        try:
            print("Moving account to step 2")
            #CLOSE ALL RUNNING POSITION ON MT5
            self.close_running_position(login)
            #RETURN ACCOUNT BALANCE ON MT5
            self.return_balance(login, challenge.account_size)
            #UPDATE TO STEP 2
            acc = self.local_accounts.get(login)
            acc.step = 2
            
            #UPDATE THE PHASE THROUGH CELERY
            move_account_to_step_2.delay(login)
            #RESET TRACKING FOR NEW PHASE
            self._reset_phase_tracking(login)
            #SEND THE NOTIFICATION
            self._send_phase_1_success_notification(login, challenge)

            logger.info(f"Account {login} successfully moved to Phase 2")
        except Exception as err:
            logger.debug(f"Error processing Phase 1 pass for {login}: {str(err)}")

    def _challenge_passed(self,acc:AccountData,challenge:PropFirmChallengeData):
        """Handle complete challenge success - eligible for funded account"""
        try:
            #LOCK ACCOUNT
            self.lock_account.add(acc.login)
            #PERSIST ACCOUNT DATA
            self.persist_account_data(acc.login)
            #PASS ACCOUNT THROUGH CELERY
            pass_account.delay(acc.login, challenge.id)
            #DISABLE TRADING ACCESS
            self.disable_trading_account(acc.login)
            #RESET PHASE TRACKING
            self._reset_phase_tracking(acc.login)
            #Lock account so there wont be a rule monitoring for it
            logger.info(f"Challenge PASSED for account {acc.login}")

        except Exception as err:
            logger.debug(f"Error processing challenge pass for {acc.login}: {str(err)}")

    def _challenge_failed(self, login: int, reasons:List[ViolationDict], challenge:PropFirmChallengeData):
        """Handle complete challenge failure"""
        try:
            # Update user status
            failure_type = "failed"
            logger.info(f"Decided failure type: {failure_type}")
            
            monitor.lock_account.add(login)

            #FAIL ACCOUNT THROUGH CELERY
            fail_account.delay(login, failure_type, reasons)
            #DISABLE TRADING ACCOUNT
            self.disable_trading_account(login)
            #FIRST PERSIST ACCOUNT DATA
            self.persist_account_data(login)
            #THEN RESET THE PHASE TRACKING
            self._reset_phase_tracking(login)
            #SEND NOTIFICATION ALERT
            self._send_challenge_failure_notification(login, challenge, reasons)

            self.lock_account.discard(login)
            logger.info(f"Successfully processed challenge failure {login}")

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

        if login in self.deals:
            self.deals[login] = []

        if login in self.violation_counts:
            self.violation_counts[login] = {}
        
        logger.info(f"Phase 2: Fresh total drawdown tracking started at {account.equity}")
    
    def _clear_drawdowns(self, login: int):
        self.total_drawdown.pop(login, None)       # remove total dd for this account
        self.daily_drawdowns.pop(login, None)      # remove all daily dd for this account

    def OnTick(self, symbol: str, tick:TickData):
        try:
            self.symbol[symbol] = tick
            #Update the currency conversion
            self.converter.update_from_tick(symbol, tick.bid, tick.ask)
            accounts =  self.get_accounts_with_symbol(symbol)
            for acc in accounts:
                # print("Running account", acc.login)
                if acc.login in self.lock_account:
                    continue

                try:
                    # Add to lock set
                    self.lock_account.add(acc.login)
                    _acc = self.update_account_equity(acc.login)
                    self.update_account_watermarks(_acc.login, _acc.balance, _acc.equity)
                    dd = self.update_drawdown(acc.login)
                    total_dd = self.update_total_drawdown(acc.login)

                    challenge = self.account_challenge.get(acc.login)
                    if not challenge:
                        continue
                
                    broken_rules = self.rule_checker.check_account_rules(acc, challenge, dd, total_dd) 
                    if broken_rules:
                        print(f"Handling account violation - {acc.login}")
                        self._handle_account_rules_violation(acc.login, broken_rules)

                except Exception as err:
                    logger.error(f"Error processing account {acc.login}: {err}", exc_info=True)
                finally: 
                    self.lock_account.discard(acc.login)

        except Exception as err:
            logger.error("Error processing OnTick", exc_info=True)
            traceback.print_exc()
    
    def get_accounts_with_symbol(self, symbol: str) -> List[AccountData]:
        accounts = []
        for login, account in self.local_accounts.items():
            # Skip accounts that are in the lock set
            if login in self.lock_account:
                continue
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

                # Validate tick data
                if price.bid <= 0 or price.ask <= 0:
                    logger.warning(f"Invalid tick data for {pos.symbol}: bid={price.bid}, ask={price.ask}")
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

                quote_currency = self.converter.get_quote_currency(pos.symbol)
                pnl = self.converter.to_usd(pnl, quote_currency)

                profit += pnl
                # print(f"Profit-{profit}")
                position_margin = (volume_in_lots * contract_size * margin_price) / leverage
                margin += position_margin

                # update position state
                pos.profit = float(pnl)
                # pos.time_update = int(time.time())

            equity = Decimal(balance) + profit
            free_margin = equity - margin

            # logger.info(f"Final calculation: Total Profit-{profit} Total Margin-{margin} Equity-{equity} Free Margin-{free_margin}")

            # Validate final equity calculation
            if equity < 0:
                logger.error(f"Negative equity calculated for {login}: {equity}")

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

            # Update highs and lows
            if account.equity > dd.equity_high:
                dd.equity_high = account.equity

            if dd.equity_low == 0 or account.equity < dd.equity_low:
                dd.equity_low = account.equity

            # Recalculate drawdown %
            if dd.equity_high > 0:
                dd.drawdown_percent = (account.equity - dd.equity_high) / dd.equity_high * 100
            # if dd.equity_high > 0:
            #     dd.drawdown_percent = (
            #         (dd.equity_high - dd.equity_low) / dd.equity_high * 100
            #     )
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
            
            equity_peak = 0
            challenge = self.account_challenge.get(login, None)
            competition = self.account_competition.get(login, None)
            if challenge:
                equity_peak = Decimal(challenge.account_size)
            elif competition:
                equity_peak = Decimal(competition.starting_balance)
            else:
                return None

            td = self.total_drawdown.get(login, None)
            if not td:
                td = self.total_drawdown[login] = AccountTotalDrawdownData(
                    login=login,
                    equity_peak=equity_peak,
                    equity_low=account.equity,
                    drawdown_percent=Decimal("0"),
                )

            # Update peak if current equity is higher
            if account.equity > td.equity_peak:
                td.equity_peak = account.equity
                # td.equity_low = account.equity  # reset low after new peak
            else:
                # Update equity low if lower
                if td.equity_low == 0 or account.equity < td.equity_low:
                    td.equity_low = account.equity

            # Recalculate drawdown %
            if td.equity_peak > 0:
                td.drawdown_percent = (Decimal(account.equity) - Decimal(td.equity_peak) / Decimal(td.equity_peak) * Decimal(100))
                # td.drawdown_percent = ((Decimal(td.equity_peak) - Decimal(td.equity_low)) / Decimal(td.equity_peak)) * 100

            # print(f"FINAL: PEAK-{td.equity_peak} LOW-{td.equity_low}")
            return td
        
        except Exception as err:
            logger.debug(f"Error updating account total drawdown: {str(err)}")
            traceback.print_exc()

    def update_account_watermarks(self, login: int, balance: Decimal, equity: Decimal):
        watermark = self.account_watermarks.get(login)

        if not watermark:
            watermark = AccountWatermarksData(
                login=login,
                hwm_balance=balance, lwm_balance=balance,
                hwm_equity=equity, lwm_equity=equity
            )
            self.account_watermarks[login] = watermark
            return

        # High-water marks
        if balance > watermark.hwm_balance:
            watermark.hwm_balance = balance
            watermark.lwm_balance = balance  # reset low when new high found

        if equity > watermark.hwm_equity:
            watermark.hwm_equity = equity
            watermark.lwm_equity = equity  # reset low when new high found

        # Low-water marks
        if balance < watermark.lwm_balance:
            watermark.lwm_balance = balance

        if equity < watermark.lwm_equity:
            watermark.lwm_equity = equity

        # Save back
        self.account_watermarks[login] = watermark
        

    def _send_phase_1_success_notification(self, login, challenge: PropFirmChallengeData):
        try:
            result = send_phase_1_success_task.delay(login, challenge.id)
        except Exception as err:
            logger.debug(f"Could not send phaseq success notification {login} - {str(err)}")


    def _send_challenge_failure_notification(self, login, challenge: PropFirmChallengeData, reasons: List[ViolationDict]):
        try:
            result = send_challenge_failed_mail_task.delay(login, challenge.id, reasons)
            logger.info(f"Failure alert sent to {login} ")
        except Exception as err:
            logger.debug(f"Could not send challenge failure notification {login} - {str(err)}")


    def cleanup_unused_symbols(self):
        """Remove tick data for symbols not in any active positions"""
        used_symbols = set()
        for positions in self.positions.values():
            for pos in positions:
                used_symbols.add(pos.symbol)
        
        # Keep a small buffer for recently used symbols
        symbols_to_remove = []
        for symbol in self.symbol:
            if symbol not in used_symbols:
                symbols_to_remove.append(symbol)
        
        # Only remove if we have too many unused symbols
        if len(symbols_to_remove) > 100:  # Configurable threshold
            for symbol in symbols_to_remove[:50]:  # Remove oldest 50
                del self.symbol[symbol]
            logger.info(f"Cleaned up {len(symbols_to_remove[:50])} unused symbols")


    def should_broadcast(self, login: int) -> bool:
        """Check if enough time has passed since last update"""
        now = time.time()
        last_update = self.last_update_time.get(login, 0)
        # Only update if 30 minutes (1800 seconds) have passed
        if now - last_update >= 1800.0:
            self.last_update_time[login] = now
            return True
        return False
    
    def persist_account_data(self, login: int):
        # --- Daily Drawdowns ---
        dds = self.daily_drawdowns.get(login)
        if dds:
            latest_date = max(dds.keys())
            latest_dd = {login: {latest_date: dds[latest_date]}}
            serialized_dd = json.dumps(make_json_safe(latest_dd), cls=EnhancedJSONEncoder)
            process_drawdowns_task.delay(serialized_dd)

        # --- Total Drawdown ---
        td = self.total_drawdown.get(login)
        if td:
            total_dd = {login: td}
            serialized_total_dd = json.dumps(make_json_safe(total_dd), cls=EnhancedJSONEncoder)
            process_total_drawdowns_task.delay(serialized_total_dd)

        # --- Account Watermarks ---
        wm = self.account_watermarks.get(login)
        if wm:
            watermarks = {login: wm}
            serialized_watermarks = json.dumps(make_json_safe(watermarks), cls=EnhancedJSONEncoder)
            process_account_watermarks_task.delay(serialized_watermarks)


    def disable_trading_account(self, login):
        try:
            #DISABLE ACCOUNT AND CLOSE POSITIONS ON MT5
            logger.info("Start disabling account")
            p.produce(
                "disable_trading", 
                json.dumps({"login":login}, cls=EnhancedJSONEncoder).encode("utf-8")
            )
            p.flush()
        except Exception as disable_error:
            logger.error(f"Failed to disable trading for {login}: {disable_error}")

    def return_balance(self, login, target_balance):
        p.produce(
            "return_balance", 
            json.dumps({"login":login, "balance":target_balance}, cls=EnhancedJSONEncoder).encode("utf-8")
        )
        p.flush()

    def close_running_position(self, login):
        p.produce(
            "close_positions",
            json.dumps({"login": login}, cls=EnhancedJSONEncoder).encode("utf-8")
        )
        p.flush()

    ###############################################################################################################################
    ################# WEBSOCKET USAGE
    ###############################################################################################################################
    def _broadcast_account_stats(self, login: int):
        """Send real-time stats to Redis for WebSocket subscribers"""            
        try:
            stats = self.account_stat(login)
            
            # Add drawdown data
            today = now().date()
            account = self.local_accounts.get(login, None)
            daily_dd = self.daily_drawdowns.get(login, {}).get(today)
            total_dd = self.total_drawdown.get(login)
            
            watermark = self.account_watermarks.get(login)

            stats.update({
                'daily_drawdown_percent': float(daily_dd.drawdown_percent) if daily_dd else 0,
                'total_drawdown_percent': float(total_dd.drawdown_percent) if total_dd else 0,
                'equity_peak': float(total_dd.equity_peak) if total_dd else 0,
                'equity_low': float(total_dd.equity_low) if total_dd else 0,
                'daily_equity_high': float(daily_dd.equity_high) if daily_dd else 0,
                'daily_equity_low': float(daily_dd.equity_low) if daily_dd else 0,
                'timestamp': int(time.time()),
                'hwm_equity': float(watermark.hwm_equity) if watermark else 0,
                'hwm_balance': float(watermark.hwm_balance) if watermark else 0,
                'lwm_equity': float(watermark.lwm_equity) if watermark else 0,
                'lwm_balance': float(watermark.lwm_balance) if watermark else 0,
            })
            
            group_name = f"account_{login}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "account_update",  # This maps to consumer handler
                    "data": json.dumps(stats, default=decimal_default),
                }
            )
            print("Broadcasted:", login)
            
        except Exception as e:
            logger.error(f"Error broadcasting stats for {login}: {e}")
            traceback.print_exc()


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
                winning += Decimal(pos.profit)
                winning_count += 1
            elif pos.profit < 0:
                losing += Decimal(pos.profit)
                losing_count += 1

        # Challenge info
        challenge = self.account_challenge.get(login)
        profit_target = Decimal(0)
        if challenge:
            profit_target = (challenge.profit_target_percent / Decimal(100)) * Decimal(challenge.account_size)

        # Win ratio
        win_ratio = (winning_count / len(positions) * 100) if positions else 0

        # Profit factor
        if losing_count == 0 and winning_count > 0:
            profit_factor = None
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
    

    def analyze_account_rating(self):
        try:
            accounts_to_rate=[]
            logger.info("Analyzing account rating data")
            for login, account in self.local_accounts.items():
                watermark = self.account_watermarks.get(login, [])
                if not watermark:
                    continue
                stat = self.account_stat(login)

                # Convert Decimals to strings for serialization
                serialized_stat = {}
                for key, value in stat.items():
                    if isinstance(value, Decimal):
                        serialized_stat[key] = str(value)
                    else:
                        serialized_stat[key] = value

                accounts_to_rate.append(
                    {
                        'watermark': {
                            'login': watermark.login,
                            'hwm_balance': str(watermark.hwm_balance),
                            'lwm_balance': str(watermark.lwm_balance),
                            'hwm_equity': str(watermark.hwm_equity),
                            'lwm_equity': str(watermark.lwm_equity),
                        },
                        'stat': serialized_stat
                    }
                )
            logger.info(f"Transferring Analyzed data to celery {len(accounts_to_rate)}")
            update_account_ratings.delay(accounts_to_rate)
        except Exception as err:
            logger.info("Error while analyzing account rating")
            traceback.print_exc()










c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "rule-engine",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000
})

c.subscribe([
    "account_challenge_initiate", "market.ticks", "accounts.state", "accounts.load", 
    "accounts.position", "accounts.position.remove", "accounts.position.update", "accounts.deal", 
    "accounts.deal.remove", "accounts.deal.update", "account.to.phase2", "account.clear", 
    "persist_valid_data", "account.fail", "account.lock", "account.unlock", "account.fund"
])

monitor = InMemoryPropMonitoring()
while True:
    msg = c.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Error:", msg.error())
        continue
    
    try:
        if msg.topic() == "market.ticks":
            tick = TickData(**json.loads(msg.value().decode("utf-8")))
            monitor.OnTick(tick.symbol, tick)
            # print(f"Received tick {tick.symbol}")

        elif msg.topic() == "accounts.state":
            account = AccountData(**json.loads(msg.value().decode("utf-8")))
            monitor.update_account(account)
            print(f"Updated account {account.login}")

        elif msg.topic() == "account_challenge_initiate":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            account_data = data['account']
            challenge = PropFirmChallengeData(**data['challenge'])

            #Update Vital account data
            monitor.local_accounts.get(login).created_at = account_data['created_at']
            monitor.local_accounts.get(login).active = account_data['active']
            monitor.local_accounts.get(login).step = account_data['step']
            #Map the account challenge
            monitor.account_challenge[login] = challenge
            print(f"Account challenge received {login}")

        elif msg.topic() == "accounts.position":
            pos = PositionData(**json.loads(msg.value().decode("utf-8")))
            monitor.add_position(pos)
            print(f"Added Position {pos.login}")

        elif msg.topic() == "accounts.position.update":
            pos = PositionData(**json.loads(msg.value().decode("utf-8")))
            monitor.update_position(pos)
            print(f"Added Position {pos.login}")
        
        elif msg.topic() == "accounts.position.remove":
            pos = PositionData(**json.loads(msg.value().decode("utf-8")))
            monitor.remove_position(pos)
            print(f"Position Removed {pos.position_id}, , Profit: {pos.profit}")
        
        elif msg.topic() == "accounts.deal":
            deal = DealData(**json.loads(msg.value().decode("utf-8")))
            monitor.add_deal(deal)
            print(f"Added Deal {deal.login}")
        
        elif msg.topic() == "accounts.deal.update":
            deal = DealData(**json.loads(msg.value().decode("utf-8")))
            monitor.update_deal(deal)
            print(f"Updated Deal {deal.login}")

        elif msg.topic() == "accounts.deal.remove":
            deal = DealData(**json.loads(msg.value().decode("utf-8")))
            monitor.remove_deal(deal)
            print(f"Deal Removed {deal.login}")

        elif msg.topic() == "account.to.phase2":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            challenge = monitor.account_challenge.get(login)
            monitor._move_to_step_2(login, challenge)
            print(f"Account moved to phase 2 {login}")
        
        elif msg.topic() == "account.clear":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            monitor.cleanup_completed_account(login)
            print(f"Cleared account details {login}")
        
        elif msg.topic() == "account.fail":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            broken_rules:List[ViolationDict] = data["broken_rules"]

            monitor.lock_account.add(login)
            monitor.persist_account_data(login)
            monitor._handle_account_rules_violation(login, broken_rules)
            print("Failing account")
            challenge = monitor.account_challenge.get(login)
            if not challenge:
                monitor._challenge_failed(login, broken_rules, challenge)
        
        elif msg.topic() == "account.fund":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            acc = monitor.local_accounts.get(login)
            if acc:
                acc.step = 3
                monitor.lock_account.discard(login)
                monitor._reset_phase_tracking(login)

        elif msg.topic() == "account.unlock":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            acc = monitor.local_accounts.get(login)
            if acc:
                monitor.lock_account.discard(login)

        elif msg.topic() == "account.lock":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            acc = monitor.local_accounts.get(login)
            if acc:
                monitor.lock_account.add(login)

        elif msg.topic() == "persist_valid_data":
            today = date.today()
            yesterday = today - timedelta(days=1)

            # Prepare only today and yesterday's drawdowns for each account
            filtered_dds = {}
            for login, dd_data in monitor.daily_drawdowns.items():
                if not dd_data:
                    continue

                filtered_dds[login] = {}
                for dd_date, dd in dd_data.items():
                    if dd_date in (yesterday, today):
                        filtered_dds[login][dd_date] = dd

                # If no entries match, skip that account
                if not filtered_dds[login]:
                    del filtered_dds[login]

            # Persist filtered data
            serialized_dd = json.dumps(make_json_safe(filtered_dds), cls=EnhancedJSONEncoder)
            process_drawdowns_task.delay(serialized_dd)
            # Still persist total drawdown and watermarks for all accounts
            serialized_total_dd = json.dumps(make_json_safe(monitor.total_drawdown), cls=EnhancedJSONEncoder)
            process_total_drawdowns_task.delay(serialized_total_dd)
            serialized_watermarks = json.dumps(make_json_safe(monitor.account_watermarks), cls=EnhancedJSONEncoder)
            process_account_watermarks_task.delay(serialized_watermarks)
    
    except Exception as err:
        print(f"ERROR OCCURED: {str(err)}")
        traceback.print_exc()