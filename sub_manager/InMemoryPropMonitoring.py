from confluent_kafka import Producer
import MT5Manager, time, traceback
from datetime import date
from datetime import time as dtime
from django.utils.timezone import now
from typing import List, Dict, Tuple, Union
from stanum_web.tasks import *
from asgiref.sync import async_to_sync
from sub_manager.InMemoryData import *
from sub_manager.InMemoryRuleChecker import *
from sub_manager.logging_config import get_prop_logger
from sub_manager.producer import redis_client

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

        self.violation_counts: Dict[int, Dict[str, int]] = {} 

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

    def _handle_trade_violations(self, login, symbol, violations:List[ViolationDict]):
        if violations:
            compiled_violations:List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]] = []
            for violation in violations:
                violation_type =violation['type']
                if login not in self.violation_counts:
                    self.violation_counts[login] = {}
                if violation_type not in self.violation_counts[login]:
                    self.violation_counts[login][violation_type] = 0
                    
                # Increment count
                self.violation_counts[login][violation_type] += 1
                count = self.violation_counts[login][violation_type]
                severity:Literal['warning', 'severe', 'critical'] = 'warning'
                if count == 1:
                    severity = 'warning'
                elif count == 2:
                    severity = 'severe'  
                elif count >= 3:
                    severity = 'critical'

                compiled_violations.append((violation, severity))
            #Send email notification about the violation
            trade_rule_violation_alert.delay(login, compiled_violations, symbol,)


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
            # 1. First reset account on MT5 (close positions and reset account_size)
            # self.bridge.reset_account(login, challenge.account_size)
            # 2. Then clear from memory
            self._clear_positions(login)
            self._clear_deals(login)
            # 4. Update database and memory state
            acc = self.local_accounts.get(login)
            acc.step = 2

            #Move the DB account to phase 2 on celery
            move_account_to_step_2.delay(login)

            # 5. Reset tracking for new phase
            self._reset_phase_tracking(login)
            # 6. Send notification
            self._send_phase_1_success_notification(login, challenge)

            logger.info(f"Account {login} successfully moved to Phase 2")
        except Exception as err:
            logger.debug(f"Error processing Phase 1 pass for {login}: {str(err)}")

    def _challenge_passed(self,acc:AccountData,challenge:PropFirmChallengeData):
        """Handle complete challenge success - eligible for funded account"""
        try:
            #Pass account in celery
            pass_account.delay(acc.login, challenge.id)

            # self.bridge.disable_challenge_account_trading(acc.login)
            self.cleanup_completed_account(acc.login)
            logger.info(f"Challenge PASSED for account {acc.login}")

        except Exception as err:
            logger.debug(f"Error processing challenge pass for {acc.login}: {str(err)}")

    def _challenge_failed(self, login: int, reasons:List[ViolationDict], challenge:PropFirmChallengeData):
        """Handle complete challenge failure"""
        try:
            
            # Update user status
            failure_type = "failed"
            if any("MAX_DAYS_EXCEEDED" == reason['type'] for reason in reasons):
                failure_type = "expired"
            logger.info(f"Decided failure type: {failure_type}")
            
            #Update DB in Celery
            fail_account.delay(login, failure_type, reasons)

            # Try to disable account - if this fails, we still have the data
            try:
                #DISABLE ACCOUNT AND CLOSE POSITIONS ON MT5
                logger.info("Start disabling account")
                # self.bridge.disable_challenge_account_trading(login)
            except Exception as disable_error:
                logger.error(f"Failed to disable trading for {login}: {disable_error}")
                # Continue anyway - account is marked as failed in database

            #CLEAR IN MEMORY POSITION
            self._clear_positions(login)
            #CLEAR IN MEMORY DEAL
            self._clear_deals(login)
            #SEND NOTIFICATION ALERT
            self._send_challenge_failure_notification(login, challenge, reasons)

            # Finally cleanup (this removes all tracking data)
            self.cleanup_completed_account(login)
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
            # print(f"ACCOUNTS WITH SYMBOL({symbol})", len(accounts))
            for acc in accounts:
                # print("Running account", acc.login)
                if acc.login in self.lock_account:
                    continue
                
                # Add to lock set
                self.lock_account.add(acc.login)

                try:
                    _acc = self.update_account_equity(acc.login)
                    self.update_account_watermarks(_acc.login, _acc.balance, _acc.equity)
                    dd = self.update_drawdown(acc.login)
                    total_dd = self.update_total_drawdown(acc.login)
                    
                    if self.should_update_leaderboard(acc.login):  # Throttle this
                        self.update_competition_metrics(acc.login)

                    challenge = self.account_challenge.get(acc.login)
                    if not challenge:
                        continue
                    
                    #broadcast after equity/drawdown updates
                    if self.should_broadcast(acc.login):
                        self._broadcast_account_stats(acc.login)

                    broken_rules = self.rule_checker.check_account_rules(acc, challenge, dd, total_dd) 
                    
                    if len(broken_rules) == 0:
                        #Check If the rules configuration is not for a funded account
                        if challenge.challenge_class not in ['skill_check_funding', 'challenge_funding']:
                            # Check if minimum days requirement met
                            if not self.rule_checker._check_min_days(acc, challenge):
                                # logger.info(f"NO ACCOUNT VIOLATIONS BUT MIN DAYS NOT REACHED YET {acc.login}")
                                continue

                            # logger.info(f"NO ACCOUNT VIOLATIONS BUT TARGET PROFIT NOT YET MADE {acc.login}")
                            continue
                    else:
                        print("Handling account violation")
                        self.lock_account.add(acc.login)
                        self._handle_account_rules_violation(acc.login, broken_rules)
                        print("Failing account")
                        self._challenge_failed(acc.login, broken_rules, challenge)

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

                # print(f"Position {pos.symbol}: Action={pos.action}, Volume={pos.volume}, "
                # f"OpenPrice={pos.price_open}, CurrentBid={current_bid}, CurrentAsk={current_ask}")
                # print(f"Calculated PnL: {pnl}, Contract Size: {contract_size}")
                # print(f"Volume in lots: {volume_in_lots}")
                # print("---")

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


    def _handle_account_rules_violation(self, login: int, violations: List[ViolationDict]):
        """Handle rule violations - warnings or account restrictions"""
        try:
            compiled_violations:List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]] =  []
            for violation in violations:
                compiled_violations.append((violation, 'severe'))
            
            #Send email notification about the violation
            account_rule_violation_log.delay(login, compiled_violations)
            # logger.info(f"Violations logged for {login}: {violations}")
            
        except Exception as e:
            logger.debug(f"Error logging violations for {login}: {e}")
        

    def _send_phase_1_success_notification(self, login, challenge: PropFirmChallengeData):
        try:
            result = send_phase_1_success_task.delay(login, challenge.id)
        except Exception as err:
            logger.debug(f"Could not send phase q success notification {login} - {str(err)}")


    def _send_challenge_failure_notification(self, login, challenge: PropFirmChallengeData, reasons: List[ViolationDict]):
        try:
            result = send_challenge_failed_mail_task.delay(login, challenge.id, reasons)
            logger.info(f"Failure alert sent to {login} ")
        except Exception as err:
            logger.debug(f"Could not send challenge failure notification {login} - {str(err)}")


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


    def update_user_metrics(self, login: int):
        """
        Calculate and store all user metrics in Redis
        Called after significant events (position close, equity change, etc.)
        """
        try:
            stats = self.calculate_user_metrics(login)
            if not stats:
                return
            
            # Store all metrics in Redis hash
            redis_client.hset(f"user:{login}", mapping={
                "username": stats["username"],
                "starting_balance": str(stats["starting_balance"]),
                "current_equity": str(stats["current_equity"]),
                "profit": str(stats["profit"]),
                "return_percent": str(stats["return_percent"]),
                "max_drawdown": str(stats["max_drawdown"]),
                "total_trades": str(stats["total_trades"]),
                "winning_trades": str(stats["winning_trades"]),
                "win_rate": str(stats["win_rate"]),
                "score": str(stats["score"]),
                "updated_at": str(int(time.time()))
            })
            
            # If competition account, update leaderboard sorted set
            if self.is_competition_account(login):
                redis_client.zadd("competition:leaderboard", {login: stats["score"]})
                
                # Broadcast update to WebSocket
                self.broadcast_competition_update()
            
            # Broadcast to individual account viewers
            self.broadcast_account_update(login, stats)
            
        except Exception as e:
            logger.error(f"Error updating metrics for {login}: {e}")
            traceback.print_exc()



    #===============================================================================================
    # COMPETITION
    #===============================================================================================
    def should_update_leaderboard(self, login: int) -> bool:
        """Check if enough time has passed since last update"""
        now = time.time()
        last_update = self.last_update_time.get(login, 0)
        # Only update if 5 seconds have passed
        if now - last_update >= 10.0:
            self.last_update_time[login] = now
            return True
        return False
    
    def should_broadcast(self, login:int) -> bool:
        now = time.time()
        last_broadcast = self.last_broadcast_time.get(login, 0)
        # Only update if 5 seconds have passed
        if now - last_broadcast >= 10.0:
            self.last_broadcast_time[login] = now
            return True
        return False
    
    def update_competition_metrics(self, login: int):
        """
        Calculate all metrics, update Redis, and broadcast to frontend
        NO database operations here (fast path)
        """
        try:
            # logger.info(f"Broadcasting: {login} ")
            # Get competition UUID from Redis
            competition_uuid = redis_client.hget(f"user:{login}", "competition_uuid")
            # logger.info(f"Competition uuid: {competition_uuid}")
            if not competition_uuid:
                return  # Not in competition
            
            # Check if competition is still active
            if not self.is_competition_active(competition_uuid):
                logger.info(f"Competition not active")
                return  # Ended, don't update
            
            # Calculate all metrics
            stats = self.calculate_user_metrics(login)
            # logger.info(f"User metrics: {stats}")
            if not stats:
                return
            
            # Update Redis (fast - ~0.1ms)
            redis_client.hset(f"user:{login}", mapping={
                k: str(v) for k, v in stats.items()
            })
            
            # Update leaderboard sorted set
            redis_client.zadd(
                f"competition:{competition_uuid}:leaderboard",
                {login: stats["score"]}
            )
            
            # logger.info("Rounding up broadcasting")
            # Broadcast to frontend via Channels
            self.broadcast_competition_leaderboard(competition_uuid)
            # logger.info("Broadcasted")

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error updating competition metrics for {login}: {e}")
    

    def calculate_user_metrics(self, login: int) -> Optional[dict]:
        """Calculate all competition metrics"""
        try:
            account = self.local_accounts.get(login)
            competition = self.account_competition.get(login)
            
            if not competition:
                return None
            
            # Drawdown data
            total_dd = self.total_drawdown.get(login)
            
            # Calculations
            starting_balance = Decimal(competition.starting_balance)
            current_equity = account.equity
            profit = current_equity - starting_balance
            return_percent = (profit / starting_balance * 100) if starting_balance > 0 else Decimal("0")
            
            max_drawdown = abs(total_dd.drawdown_percent) if total_dd else Decimal("0")
            
            # Trade stats from Redis
            total_trades = int(redis_client.hget(f"user:{login}", "total_trades") or 0)
            winning_trades = int(redis_client.hget(f"user:{login}", "winning_trades") or 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else Decimal("0")
            
            # Competition score (return / drawdown ratio)
            score = float(return_percent) / (float(max_drawdown) + 0.01)
            
            return {
                "login": login,
                "username": f"Trader_{login}",
                "competition_uuid": str(competition.uuid),
                "starting_balance": float(starting_balance),
                "current_equity": float(current_equity),
                "profit": float(profit),
                "return_percent": float(return_percent),
                "max_drawdown": float(max_drawdown),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "win_rate": float(win_rate),
                "score": score,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error calculating metrics for {login}: {e}")
            return None

    def is_competition_active(self, competition_uuid: str) -> bool:
        """Check if competition is still active"""
        status = redis_client.hget(f"competition:{competition_uuid}:meta", "status")
        
        if status != "active":
            return False
        
        # Check end date
        end_date_str = redis_client.hget(f"competition:{competition_uuid}:meta", "end_date")
        if end_date_str:
            end_date = datetime.fromisoformat(end_date_str)
            if datetime.now(timezone.utc) > end_date:
                # Competition just ended, finalize it
                finalize_competition_task.delay(competition_uuid)
                return False
        
        return True


    def broadcast_competition_leaderboard(self, competition_uuid: str):
        """
        Send updated leaderboard to all frontend viewers via WebSocket
        NO database operations - only Redis reads
        """
        try:
            # Get top 100 from Redis sorted set
            top_logins = redis_client.zrevrange(
                f"competition:{competition_uuid}:leaderboard",
                0, 99,
                withscores=True
            )
            
            leaderboard = []
            for rank, (login, score) in enumerate(top_logins, 1):
                user_data = redis_client.hgetall(f"user:{login}")
                
                if user_data:
                    leaderboard.append({
                        "rank": rank,
                        "login": int(login),
                        "username": user_data.get("username", ""),
                        "current_equity": float(user_data.get("current_equity", 0)),
                        "return_percent": float(user_data.get("return_percent", 0)),
                        "max_drawdown": float(user_data.get("max_drawdown", 0)),
                        "winning_trades": float(user_data.get("winning_trades", 0)),
                        "total_trades": int(user_data.get("total_trades", 0)),
                        "win_rate": float(user_data.get("win_rate", 0)),
                        "score": float(score)
                    })
            
            async_to_sync(channel_layer.group_send)(
                f"competition_{competition_uuid}",
                {
                    "type": "leaderboard_update",
                    "data": {
                        "leaderboard": leaderboard,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error broadcasting leaderboard for {competition_uuid}: {e}")






c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "rule-engine",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000
})

c.subscribe([
    "account_challenge_initiate", "account_competition_initiate", "market.ticks", 
    "accounts.state", "accounts.load", 
    "accounts.position", "accounts.position.remove", "accounts.position.update",
    "accounts.deal", "accounts.deal.remove", "accounts.deal.update",
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

        elif msg.topic() == 'account_competition_initiate':
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            competition = CompetitionData.from_dict(data['competition'])
            # print(competition)
            monitor.account_competition[login] = competition

            competition_uuid = str(competition.uuid)
            # Store competition UUID for this account in Redis
            redis_client.hset(f"user:{login}", "competition_uuid", competition_uuid)
            # Initialize trade counters
            redis_client.hset(f"user:{login}", mapping={
                "total_trades": "0",
                "winning_trades": "0",
                "username": f"Trader_{login}"
            })  
            # Initialize competition metadata (if first participant)
            if not redis_client.exists(f"competition:{competition_uuid}:meta"):
                redis_client.hset(f"competition:{competition_uuid}:meta", mapping={
                    "uuid": competition_uuid,
                    "name": competition.name,
                    "status": "active",
                    "start_date": competition.start_date.isoformat(),
                    "end_date": competition.end_date.isoformat(),
                    "starting_balance": str(competition.starting_balance)
                })

            print(f"Account {login} registered to competition {competition_uuid}")

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

            # 1. Update trade counters in Redis (FAST)
            redis_client.hincrby(f"user:{pos.login}", "total_trades", 1)
            if float(pos.profit) > 0:
                redis_client.hincrby(f"user:{pos.login}", "winning_trades", 1)
            # 2. Remove from local positions
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
    
    except Exception as err:
        print(f"ERROR OCCURED: {str(err)}")
        traceback.print_exc()