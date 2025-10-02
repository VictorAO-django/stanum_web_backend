from decimal import Decimal
import logging

class USDCurrencyConverter:
    """Allowed Currency Pair are:
       EURUSD, GBPUSD, AUDUSD, NZDUSD, USDJPY, USDCHF, USDCAD, XAUUSD
    """
    def __init__(self):
        self.rates = {
            "USD": Decimal("1.0"),
        }
        self.logger = logging.getLogger(__name__)
    
    def update_from_tick(self, symbol: str, bid: float, ask: float):
        """Update conversion rates from USD-based pairs"""
        try:
            symbol_clean = symbol.replace('.p', '')
            bid_decimal = Decimal(str(bid))
            
            # Direct USD pairs (quote currency is USD)
            if symbol_clean == "EURUSD":
                self.rates["EUR"] = bid_decimal
            elif symbol_clean == "GBPUSD":
                self.rates["GBP"] = bid_decimal
            elif symbol_clean == "AUDUSD":
                self.rates["AUD"] = bid_decimal
            elif symbol_clean == "NZDUSD":
                self.rates["NZD"] = bid_decimal
            
            # USD base pairs (base currency is USD, need to invert)
            elif symbol_clean == "USDJPY":
                self.rates["JPY"] = Decimal("1.0") / bid_decimal
            elif symbol_clean == "USDCHF":
                self.rates["CHF"] = Decimal("1.0") / bid_decimal
            elif symbol_clean == "USDCAD":
                self.rates["CAD"] = Decimal("1.0") / bid_decimal
            
            # Gold and Silver (already in USD, no conversion needed)
            # XAUUSD, XAGUSD - PnL will be directly in USD
                
        except Exception as e:
            self.logger.warning(f"Error updating rate for {symbol}: {e}")
    
    def to_usd(self, amount: Decimal, from_currency: str) -> Decimal:
        """Convert amount from any supported currency to USD"""
        if from_currency == "USD":
            return amount
        
        rate = self.rates.get(from_currency)
        if rate is None:
            self.logger.error(f"No conversion rate available for {from_currency}")
            return amount  # Return unconverted as fallback
        
        return amount * rate
    
    def get_quote_currency(self, symbol: str) -> str:
        """Extract quote currency from symbol"""
        symbol_clean = symbol.replace('.p', '')
        return symbol_clean[-3:]  # Last 3 characters