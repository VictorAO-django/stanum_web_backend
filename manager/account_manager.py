from django.db import transaction
from decimal import Decimal
from .cache import symbol_cache
from trading.models import MT5User, MT5Position, MT5Account

class AccountManager:
    def get_accounts_with_symbol(self, symbol: str):
        """Find all accounts holding open positions in this symbol."""
        logins = (
            MT5Position.objects.filter(symbol=symbol)
            .values_list("login", flat=True)
            .distinct()
        )
        return MT5User.objects.filter(login__in=logins)


    def update_account_equity(self, user: MT5User) -> MT5Account:
        """Recalculate account equity, margin, free margin."""
        positions = list(MT5Position.objects.filter(login=user.login))
        account, _ = MT5Account.objects.get_or_create(login=user.login)

        balance = account.balance
        profit = Decimal(0.0)
        margin = Decimal(0.0)

        leverage = user.leverage if user.leverage else 100  

        print(f"🔍 Starting calculation:")
        print(f"  - Balance: {balance}")
        print(f"  - Leverage: {leverage}")
        print(f"  - Positions: {len(positions)}")

        updated_positions = []

        for pos in positions:
            price = symbol_cache.get(pos.symbol)
            if not price:
                continue

            current_bid = Decimal(str(price["bid"]))
            current_ask = Decimal(str(price["ask"]))
            
            volume_in_lots = pos.volume
            contract_size = pos.contract_size or 100000

            if pos.action == 0:  # BUY position
                pnl = (current_bid - pos.price_open) * volume_in_lots * contract_size
                margin_price = current_ask
            else:  # SELL position
                pnl = (pos.price_open - current_ask) * volume_in_lots * contract_size
                margin_price = current_bid

            profit += pnl
            
            # Calculate margin for this position
            position_margin = (margin_price * volume_in_lots * contract_size) / leverage
            margin += position_margin

            print(f"Position {pos.symbol} ({'BUY' if pos.action == 0 else 'SELL'}):")
            print(f"  - Volume: {volume_in_lots} lots")
            print(f"  - Margin Price: {margin_price}")
            print(f"  - Contract Size: {contract_size}")
            print(f"  - Leverage: {leverage}")
            print(f"  - Position Margin: {position_margin}")
            print(f"  - PnL: {pnl}")
            print(f"  - Running Total Margin: {margin}")

            pos.profit = pnl
            updated_positions.append(pos)

        equity = balance + profit
        free_margin = equity - margin

        print(f"🔍 Final calculation:")
        print(f"  - Total Profit: {profit}")
        print(f"  - Total Margin: {margin}")
        print(f"  - Equity: {equity}")
        print(f"  - Free Margin: {free_margin}")

        with transaction.atomic():
            account.equity = equity
            account.margin = margin
            account.margin_free = free_margin
            account.save(update_fields=["equity", "margin", "margin_free"])

            if updated_positions:
                MT5Position.objects.bulk_update(updated_positions, ["profit"])
        
        return account