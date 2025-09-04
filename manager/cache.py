from trading.models import SymbolPrice

class SymbolCache:
    def __init__(self):
        self.prices = {}

    def update(self, symbol, bid, ask, last=None):
        self.prices[symbol] = {"bid": bid, "ask": ask, "last": last}

    def get(self, symbol):
        # Look up from internal dict instead of recursively calling self
        price = self.prices.get(symbol)
        if price:
            return price
        
        # If not in cache, fall back to DB
        snapshot = SymbolPrice.objects.filter(symbol=symbol).first()
        return {
            "bid": snapshot.bid,
            "ask": snapshot.ask,
            "last": snapshot.last,
        } if snapshot else None


# Singleton instance
symbol_cache = SymbolCache()
