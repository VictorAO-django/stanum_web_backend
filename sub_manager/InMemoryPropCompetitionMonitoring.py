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
from sub_manager.transformer import *

from confluent_kafka import Consumer, Producer
from .USDCurrencyConverter import USDCurrencyConverter

logger = get_prop_logger('monitoring')


def decimal_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

class InMemoryPropCompetitionMonitoring:
    def __init__(self):
        self.converter = USDCurrencyConverter()
        self.local_accounts: Dict[int, AccountData] = {}
        self.positions: Dict[int, List[PositionData]] = {}
        self.account_competition: Dict[int, CompetitionData] = {}

        self.symbol:Dict[str, TickData] = {}

        self.daily_drawdowns: Dict[int, Dict[date, DailyDrawdownData]] = {}
        self.total_drawdown: Dict[int, AccountTotalDrawdownData] = {}
        self.account_watermarks: Dict[int, AccountWatermarksData] = {}

        self.count = 0
        self.last_update_time = {}
        self.lock_account: Set[int] = set()

        logger.info("InMemoryMonitor Initialized")
    
    def remove_account(self, login):
        self.cleanup_completed_account(login)
        logger.info(f"Account Removed {login}")
    
    def update_account(self, acc: AccountData):
        try:
            self.local_accounts[acc.login] = acc
            logger.info(f"Updated Account {acc.login}")
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
            logger.info(f"Position Addedd {pos.login}")
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
                    pnl = (Decimal(pos.price_open) - current_ask) * volume_in_lots * contract_size
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

            equity = Decimal(balance) + Decimal(profit)
            free_margin = Decimal(equity) - Decimal(margin)

            # logger.info(f"Final calculation: Total Profit-{profit} Total Margin-{margin} Equity-{equity} Free Margin-{free_margin}")

            # Validate final equity calculation
            if equity < Decimal(0):
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
            
            competition = self.account_competition.get(login, None)
            if not competition:
                return
            
            equity_peak = Decimal(competition.starting_balance)
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


    def persist_account_data(self, login: int):
        # --- Total Drawdown ---
        td = self.total_drawdown.get(login)
        if td:
            total_dd = {login: td}
            serialized_total_dd = json.dumps(make_json_safe(total_dd), cls=EnhancedJSONEncoder)
            process_total_drawdowns_task.delay(serialized_total_dd)


    def cleanup_competition_memory(self, competition_uuid: str):
        """
        Clean up in-memory state for ended competition
        Free up RAM by removing competition-related data
        """
        try:
            logger.info(f"Cleaning up in-memory state for competition {competition_uuid}")
            
            # 1. Find all accounts in this competition
            accounts_to_cleanup = []
            for login, competition in self.account_competition.items():
                if str(competition.uuid) == competition_uuid:
                    accounts_to_cleanup.append(login)
            
            # 2. Remove competition references from memory
            for login in accounts_to_cleanup:
                # Remove from account_competition mapping
                if login in self.account_competition:
                    del self.account_competition[login]
                    logger.debug(f"Removed competition reference for account {login}")
                
            logger.info(f"Cleaned up {len(accounts_to_cleanup)} accounts from competition {competition_uuid}")
            
        except Exception as e:
            logger.error(f"Error cleaning up competition memory: {e}", exc_info=True)







c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "rule-engine",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000
})

c.subscribe([
    "account_competition_initiate", "competition.control",
    "market.ticks", "accounts.state", "accounts.load", 
    "accounts.position", "accounts.position.remove", "accounts.position.update",
    "persist_valid_data", "persist_login_data", 
    "account.lock.competition", "account.unlock.competition",
])

monitor = InMemoryPropCompetitionMonitoring()
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
            print(f"Account {login} registered to competition {competition_uuid}")

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
            # 2. Remove from local positions
            monitor.remove_position(pos)

            print(f"Position Removed {pos.position_id}, , Profit: {pos.profit}")

        elif msg.topic() == "account.unlock.competition":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            acc = monitor.local_accounts.get(login)
            if acc:
                monitor.lock_account.discard(login)

        elif msg.topic() == "account.lock.competition":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            acc = monitor.local_accounts.get(login)
            if acc:
                monitor.lock_account.add(login)

        elif msg.topic() == "persist_login_data":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])

            monitor.persist_account_data(login)

        elif msg.topic() == "persist_valid_data":
            unlocked_total_dd = {
                login: dd for login, dd in monitor.total_drawdown.items()
                if login not in monitor.lock_account
            }
            serialized_total_dd = json.dumps(make_json_safe(unlocked_total_dd), cls=EnhancedJSONEncoder)
            process_total_drawdowns_task.delay(serialized_total_dd)

        elif msg.topic() == "competition.control":
            data = json.loads(msg.value().decode("utf-8"))
            action = data['action']

            if action == "finalize_competition":
                competition_uuid = data['competition_uuid']
                # Finalize competition immediately
                persist_competition_results_task.delay(
                    competition_uuid=competition_uuid
                )
                # Clean up in-memory state
                monitor.cleanup_competition_memory(competition_uuid)
                logger.info(f"Received finalize signal for competition {competition_uuid}")
                
                

    except Exception as err:
        print(f"ERROR OCCURED: {str(err)}")
        traceback.print_exc()