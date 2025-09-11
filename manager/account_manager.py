from django.db import transaction
from typing import Literal
from decimal import Decimal
from .cache import symbol_cache
from trading.models import MT5User, MT5Position, MT5Account, AccountDrawdown, AccountTotalDrawdown, AccountWatermarks
from django.utils.timezone import now
from django.utils import timezone

class AccountManager:
    def get_accounts_with_symbol(self, symbol: str):
        """Find all accounts holding open positions in this symbol."""
        logins = (
            MT5Position.objects.filter(symbol=symbol, closed=False)
            .values_list("login", flat=True)
            .distinct()
        )
        return MT5User.objects.filter(login__in=logins)


    def update_account_equity(self, user: MT5User) -> MT5Account:
        """Recalculate account equity, margin, free margin."""
        positions = list(MT5Position.objects.filter(login=user.login, closed=False))
        account, _ = MT5Account.objects.get_or_create(login=user.login, active=True)

        balance = account.balance
        profit = Decimal(0.0)
        margin = Decimal(0.0)

        leverage = user.leverage if user.leverage else 100  

        # print(f"🔍 Starting calculation:")
        # print(f"  - Balance: {balance}")
        # print(f"  - Leverage: {leverage}")
        # print(f"  - Positions: {len(positions)}")

        updated_positions = []

        for pos in positions:
            price = symbol_cache.get(pos.symbol)
            if not price:
                continue

            current_bid = Decimal(str(price["bid"]))
            current_ask = Decimal(str(price["ask"]))
            
            volume_in_lots = pos.volume/10000
            contract_size = pos.contract_size or 100000

            if pos.action == 0:  # BUY position
                pnl = (current_bid - pos.price_open) * Decimal(volume_in_lots) * contract_size
                margin_price = current_ask
            else:  # SELL position
                pnl = (pos.price_open - current_ask) * Decimal(volume_in_lots) * contract_size
                margin_price = current_bid

            profit += pnl
            
            # Calculate margin for this position
            position_margin = (Decimal(volume_in_lots) * contract_size * margin_price) / leverage
            margin += position_margin

            # print(f"Position {pos.symbol} ({'BUY' if pos.action == 0 else 'SELL'}):")
            # print(f"  - Volume: {volume_in_lots} lots")
            # print(f"  - Margin Price: {margin_price}")
            # print(f"  - Contract Size: {contract_size}")
            # print(f"  - Leverage: {leverage}")
            # print(f"  - Position Margin: {position_margin}")
            # print(f"  - PnL: {pnl}")
            # print(f"  - Running Total Margin: {margin}")

            pos.profit = pnl
            updated_positions.append(pos)

        equity = balance + profit
        free_margin = equity - margin

        # print(f"🔍 Final calculation:")
        # print(f"  - Total Profit: {profit}")
        # print(f"  - Total Margin: {margin}")
        print(f"  - Equity: {equity}")
        # print(f"  - Free Margin: {free_margin}")

        with transaction.atomic():
            account.prev_equity = account.equity
            account.equity = equity
            account.prev_margin = account.margin
            account.margin = margin
            account.prev_margin_free = account.margin_free
            account.margin_free = free_margin
            account.profit = profit
            account.save(update_fields=["prev_equity", "equity", "prev_margin", "margin", "prev_margin_free", "margin_free", "profit"])

            if updated_positions:
                MT5Position.objects.bulk_update(updated_positions, ["profit"])
        
        return account
    
    def close_account(self, login: int, status: Literal["challenge_passed", "failed"]):
        account = MT5Account.objects.get(login=login)
        account.active = False
        account.save()

        user = account.mt5_user
        user.status = status
        user.save()

        if status == 'challenge_passed':
            print("Sending email:", status)
        
        if status == 'failed':
            print("Sending email:", status)
    

    def update_drawdown(self, login: int, equity: float):
        today = now().date()

        dd, _ = AccountDrawdown.objects.get_or_create(
            login=login,
            date=today,
            defaults={
                "equity_high": equity,
                "equity_low": equity,
                "drawdown_percent": 0,
            }
        )
        # Update highs and lows
        updated = False
        if equity > dd.equity_high:
            dd.equity_high = equity
            updated = True
        if equity < dd.equity_low or dd.equity_low == 0:
            dd.equity_low = equity
            updated = True

        # Recalculate drawdown %
        if dd.equity_high > 0:
            dd.drawdown_percent = (
                (dd.equity_high - dd.equity_low) / dd.equity_high * 100
            )
            updated = True

        if updated:
            dd.save()

        return dd

    def update_total_drawdown(self, login: int, equity: float, initial_balance: float):
        """
        Update or create the total drawdown record for an account.
        Tracks all-time equity peak and current equity lows.
        """
        obj, _ = AccountTotalDrawdown.objects.get_or_create(
            login=login,
            defaults={
                "equity_peak": initial_balance,
                "equity_low": equity,
                "drawdown_percent": 0,
            },
        )

        # Update peak if current equity is higher
        if equity > obj.equity_peak:
            obj.equity_peak = equity
            obj.equity_low = equity  # reset low after new peak
        else:
            # Update equity low if lower
            if obj.equity_low == 0 or equity < obj.equity_low:
                obj.equity_low = equity

        # Recalculate drawdown
        if obj.equity_peak > 0:
            obj.drawdown_percent = ((obj.equity_peak - obj.equity_low) / obj.equity_peak) * 100

        obj.save()
        return obj

    # Just add this method to your existing code
    def update_watermarks(self, login, balance, equity):
        watermark, created = AccountWatermarks.objects.get_or_create(
            login=login,
            defaults={
                'hwm_balance': balance, 'hwm_equity': equity,
                'lwm_balance': balance, 'lwm_equity': equity,
                'hwm_date': timezone.now(), 'lwm_date': timezone.now()
            }
        )
        
        if not created:
            # Update highs
            if balance > watermark.hwm_balance:
                watermark.hwm_balance = balance
                watermark.hwm_date = timezone.now()
            if equity > watermark.hwm_equity:
                watermark.hwm_equity = equity
                watermark.hwm_date = timezone.now()
                
            # Update lows  
            if balance < watermark.lwm_balance:
                watermark.lwm_balance = balance
                watermark.lwm_date = timezone.now()
            if equity < watermark.lwm_equity:
                watermark.lwm_equity = equity
                watermark.lwm_date = timezone.now()
                
            watermark.save()
        
        return watermark