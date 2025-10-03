import MT5Manager, time

class TickSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.last_tick_time = {}  # store last processed time per symbol
    
    def OnTick(self, symbol: str, tick:MT5Manager.MTTick):
        now = time.time()
        last_time = self.last_tick_time.get(symbol, 0)

        if now - last_time >= 30:
            self.last_tick_time[symbol] = now
            self.bridge.tick(symbol, tick)
