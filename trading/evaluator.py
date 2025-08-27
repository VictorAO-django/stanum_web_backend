from datetime import date
from trading.models import MT5Account
class ChallengeRulesEvaluator:
    def __init__(self, challenge_account: MT5Account):
        self.account = challenge_account
        self.challenge = challenge_account.challenge
    
    def check_daily_drawdown(self, current_equity, daily_start_balance):
        max_loss = daily_start_balance * (self.challenge.max_daily_loss_percent / 100)
        if current_equity < daily_start_balance - max_loss:
            return False, "Daily Drawdown Exceeded"
        return True, None

    def check_total_drawdown(self, current_equity):
        max_loss = self.account.start_balance * (self.challenge.max_total_loss_percent / 100)
        if current_equity < self.account.start_balance - max_loss:
            return False, "Max Total Drawdown Exceeded"
        return True, None

    def check_profit_target(self, current_balance):
        target = self.account.start_balance * (1 + self.challenge.profit_target_percent / 100)
        if current_balance >= target:
            return True, "Profit Target Achieved"
        return False, None

    def check_min_days(self, trading_days):
        if trading_days < self.challenge.min_trading_days:
            return False, "Minimum Trading Days Not Reached"
        return True, None
