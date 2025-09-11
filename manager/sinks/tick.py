import MT5Manager, queue, threading
from manager.account_manager import AccountManager
from manager.rule_checker import RuleChecker
from trading.models import SymbolPrice, MT5User
from typing import NamedTuple
from django.utils.timezone import now
from manager.cache import symbol_cache

class TickSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
    
    def OnTick(self, symbol: str, tick:MT5Manager.MTTick):
        # print("Tick Received", symbol)
        self.bridge.tick(symbol, tick)
