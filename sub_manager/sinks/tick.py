import MT5Manager

class TickSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
    
    def OnTick(self, symbol: str, tick:MT5Manager.MTTick):
        # print("Tick Received", symbol)
        self.bridge.tick(symbol, tick)
