# models.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import MT5Account
from .evaluator import ChallengeRulesEvaluator
from .models import MT5Account

# @receiver(post_save, sender=MT5Account)
# def evaluate_account(sender, instance, created, **kwargs):
#     challenge_account = instance
#     evaluator = ChallengeRulesEvaluator(challenge_account)

#     ok, reason = evaluator.check_total_drawdown(instance.equity)
#     if not ok:
#         challenge_account.status = "failed"
#         challenge_account.fail_reason = reason
#         challenge_account.save()
