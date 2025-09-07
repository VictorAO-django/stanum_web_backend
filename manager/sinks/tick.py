import MT5Manager, queue, threading
from manager.account_manager import AccountManager
from manager.rule_checker import RuleChecker
from trading.tasks import post_tick_sink
from trading.models import SymbolPrice, MT5User
from typing import NamedTuple
from django.utils.timezone import now

class TickData(NamedTuple):
    symbol: str
    tick: 'MT5Manager.MTTickShort'

class TickSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.rule_checker = RuleChecker()
        # Create thread-safe queue
        self.tick_queue = queue.Queue(maxsize=10000)  # Adjust size as needed
        
        # Start background processor thread
        self.processor_thread = threading.Thread(target=self._process_ticks, daemon=True)
        self.processor_thread.start()
    
    def OnTick(self, symbol: str, tick):
        try:
            # Non-blocking queue push - returns immediately
            print(symbol)
            self.tick_queue.put_nowait(TickData(symbol, tick))
        except queue.Full:
            # Queue is full - either increase maxsize or handle overflow
            print(f"Queue full, dropping tick for {symbol}")
    
    def _process_ticks(self):
        """Background thread that processes ticks"""
        while True:
            try:
                tick_data = self.tick_queue.get(timeout=1)
                symbol = tick_data.symbol
                tick = tick_data.tick
                
                # print(f"Processing {symbol}")
                
                try:
                    # Test each step individually
                    bid = tick.bid
                    ask = tick.ask  
                    last = tick.last
                    # print(f"Got tick values: {bid}, {ask}, {last}")
                    
                    # DB update
                    SymbolPrice.objects.update_or_create(
                        symbol=symbol,
                        defaults={"bid": bid, "ask": ask, "last": last, "updated_at": now()}
                    )
                    # print("DB updated")
                    
                    # Account updates - THIS IS LIKELY WHERE RECURSION HAPPENS
                    account_manager = AccountManager()  # Create fresh instance
                    accounts = account_manager.get_accounts_with_symbol(symbol)
                    # print(f"Found {len(accounts)} accounts")
                        
                    for account in accounts:
                        # print(f"Processing account {account}")
                        acc = account_manager.update_account_equity(account)  # ← Recursion likely here
                        print(f"Updated equity for {account}")

                        account_manager.update_drawdown(acc.login, acc.equity)
                        account_manager.update_total_drawdown(acc.login, float(acc.equity), float(acc.mt5_user.challenge.account_size))
                        
                        violations = self.rule_checker.check_account_rules(acc) 

                        if len(violations) == 0:
                            min_day_violation = self.rule_checker._check_min_days(acc, acc.mt5_user.challenge)
                            if len(min_day_violation) == 0:
                                #Passed challenge
                                self.bridge.challenge_passed(acc.login)
                                return 
                            print(f"Waiting for min days: {min_day_violation}")
                        else:
                            self.bridge.handle_violation(acc.login, violations, "ACCOUNT")
                            self.bridge.challenge_failed(acc.login)
                            
                        print(f"Checked rules: {violations}")
                        
                except Exception as e:
                    print(f"Specific error in processing: {e}")
                    import traceback
                    traceback.print_exc()
                    
                self.tick_queue.task_done()
                
            except queue.Empty:
                continue