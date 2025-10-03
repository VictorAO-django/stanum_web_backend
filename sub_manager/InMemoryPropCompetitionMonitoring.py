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
                    
                    if self.should_update_leaderboard(acc.login):  # Throttle this
                        self.update_competition_metrics(acc.login)

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
    
    def update_competition_metrics(self, login: int):
        """
        Calculate all metrics, update Redis, and broadcast to frontend
        NO database operations here (fast path)
        """
        try:
            # logger.info(f"Broadcasting: {login} ")
            competition = self.account_competition.get(login)
            if not competition:
                return  
            
            # Get competition UUID from Redis
            competition_uuid = str(competition.uuid)
            
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








    #===============================================================================================
    # ADMIN ACTIONS
    #===============================================================================================
    def finalize_competition(self, competition_uuid: str):
        """
        Finalize competition - save final results from Redis to database
        Called when admin sends Kafka signal
        """
        try:
            logger.info(f"Finalizing competition {competition_uuid}")
            ended_at = datetime.now(timezone.utc).isoformat()
            # 1. Mark as ended in Redis
            redis_client.hset(f"competition:{competition_uuid}:meta", "status", "ended")
            redis_client.hset(f"competition:{competition_uuid}:meta", "ended_at", ended_at)
            
            # 2. Get ALL participants from Redis leaderboard
            all_participants = redis_client.zrevrange(
                f"competition:{competition_uuid}:leaderboard",
                0, -1,  # ALL participants
                withscores=True
            )
            
            if not all_participants:
                logger.warning(f"No participants found for competition {competition_uuid}")
                return
            
            # 3. Queue database persistence via Celery (async, doesn't block)
            persist_competition_results_task.delay(
                competition_uuid=competition_uuid,
                participants_data=self._prepare_results_data(all_participants)
            )
            
            # 4. Broadcast to frontend
            self.broadcast_competition_ended(competition_uuid, len(all_participants))
            
            logger.info(f"Competition {competition_uuid} finalized with {len(all_participants)} participants")
            
        except Exception as e:
            logger.error(f"Error finalizing competition {competition_uuid}: {e}", exc_info=True)


    def _prepare_results_data(self, participants: list) -> list:
        """Prepare results data for database persistence"""
        results = []
        
        for rank, (login, score) in enumerate(participants, 1):
            user_data = redis_client.hgetall(f"user:{login}")
            
            if user_data:
                results.append({
                    "rank": rank,
                    "login": int(login),
                    "username": user_data.get("username", ""),
                    "starting_balance": float(user_data.get("starting_balance", 0)),
                    "final_equity": float(user_data.get("current_equity", 0)),
                    "profit": float(user_data.get("profit", 0)),
                    "return_percent": float(user_data.get("return_percent", 0)),
                    "max_drawdown": float(user_data.get("max_drawdown", 0)),
                    "total_trades": int(user_data.get("total_trades", 0)),
                    "winning_trades": int(user_data.get("winning_trades", 0)),
                    "win_rate": float(user_data.get("win_rate", 0)),
                    "score": float(score)
                })
        
        return results


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
                
                # Clear competition_uuid from Redis user hash
                redis_client.hdel(f"user:{login}", "competition_uuid")
            
            # 3. Optional: Keep Redis data for some time (7 days) then cleanup
            # Or immediately delete if you want to free Redis memory
            ttl_days = 7
            ttl_seconds = ttl_days * 24 * 60 * 60
            
            # Set expiry on competition data
            redis_client.expire(f"competition:{competition_uuid}:meta", ttl_seconds)
            redis_client.expire(f"competition:{competition_uuid}:leaderboard", ttl_seconds)
            
            logger.info(f"Cleaned up {len(accounts_to_cleanup)} accounts from competition {competition_uuid}")
            logger.info(f"Redis data will expire in {ttl_days} days")
            
        except Exception as e:
            logger.error(f"Error cleaning up competition memory: {e}", exc_info=True)

    
    def broadcast_competition_ended(self, competition_uuid: str, total_participants: int):
        """Notify all viewers that competition has ended"""
        async_to_sync(channel_layer.group_send)(
            f"competition_{competition_uuid}",
            {
                "type": "competition_ended",
                "data": {
                    "message": "Competition has ended. Final results have been saved.",
                    "total_participants": total_participants,
                    "ended_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )








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

        elif msg.topic() == "competition.control":
            control_msg = json.loads(msg.value().decode("utf-8"))
            
            if control_msg.get("action") == "finalize_competition":
                competition_uuid = control_msg.get("competition_uuid")
                
                logger.info(f"Received finalize signal for competition {competition_uuid}")
                
                # Finalize competition immediately
                monitor.finalize_competition(competition_uuid)
                
                # Clean up in-memory state
                monitor.cleanup_competition_memory(competition_uuid)

    except Exception as err:
        print(f"ERROR OCCURED: {str(err)}")
        traceback.print_exc()