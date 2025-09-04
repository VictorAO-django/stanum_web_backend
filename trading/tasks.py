from celery import shared_task
from django.utils.timezone import now
from trading.models import SymbolPrice
from manager.account_manager import AccountManager
from manager.rule_checker import RuleChecker

@shared_task
def post_tick_sink(tick_batch):
    for symbol, tick in tick_batch:
        print(f"✅ Processing tick for {symbol}: {tick}")
        account_manager = AccountManager()
        rule_checker = RuleChecker()

        bid = tick.bid
        ask = tick.ask
        last = tick.last

        # 2. Update DB snapshot (one row per symbol)
        SymbolPrice.objects.update_or_create(
            symbol=symbol,
            defaults={"bid": bid, "ask": ask, "last": last, "updated_at": now()}
        )

        # 3. Update all accounts holding this symbol
        accounts = account_manager.get_accounts_with_symbol(symbol)
        for account in accounts:
            acc = account_manager.update_account_equity(account)
                
            violations = rule_checker.check_account_rules(acc)
            print("VIOLATIONS", violations)
            # if violations and self.bridge:
            #     self.bridge.handle_violation(account.login, violations, "MARGIN_CALL_ENTER")