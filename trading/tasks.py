import traceback
from django.db import transaction
from celery import shared_task
from django.utils.timezone import now
from utils.mailer import *
from .models import *
from account.models import *
from challenge.models import *
from django.conf import settings
from manager.InMemoryData import *

@shared_task
def send_phase_1_success_task(user_login, challenge_id,):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Phase 1 Notification Task Begin")
        mailer = Mailer([user.user.email] + settings.ADMIN_EMAILS)
        mailer.challenge_passed_1(user, challenge)

        message = (
            f"Congratulations! You just hit your {challenge.profit_target_percent}% profit target. "
            f"This marks the Phase 1 of the challenge as successful. "
            f"You can now proceed to phase 2."
        )

        with transaction.atomic():
            Notification.objects.create(
                recipient=user.user,
                sender=None,  # system-generated
                title="Phase 1 Profit Target Reached",
                message=message,
                url="/dashboard/performance",
                type="success",
                metadata={
                    "account_size": float(challenge.account_size),
                    "challenge_type": challenge.challenge_type,
                    "challenge_class": challenge.challenge_class
                },
            )

            ChallengeLog.objects.create(
                user=user,
                action='PHASE_1_PASSED',
                details=f'Moved to Phase 2',
                timestamp=now()
            )
        print("Phase 1 Notification Task stopped")
    except Exception as err:
        traceback.print_exc()


def send_phase_2_success_task(user_login, challenge_id,):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Phase 2 Notification Task Begin")
        mailer = Mailer([user.user.email] + settings.ADMIN_EMAILS)
        mailer.challenge_passed_1(user, challenge)

        message = (
            f"Congratulations! You just hit your {challenge.phase_2_profit_target_percent}% profit target. "
            f"This marks the challenge as successful. "
            f"Your funded account credentials will be sent within the next 24-48hrs"
        )

        with transaction.atomic():
            Notification.objects.create(
                recipient=user.user,
                sender=None,  # system-generated
                title="Phase 2 Profit Target Reached",
                message=message,
                url="/dashboard/performance",
                type="success",
                metadata={
                    "account_size": float(challenge.account_size),
                    "challenge_type": challenge.challenge_type,
                    "challenge_class": challenge.challenge_class
                },
            )

            ChallengeLog.objects.create(
                user=user,
                action='CHALLENGE_PASSED',
                details=f'Phase 2 Challenge completed',
                timestamp=now()
            )
        print("Phase 2 Notification Task stopped")
    except Exception as err:
        traceback.print_exc()


def send_challenge_success_mail_task(user_login, challenge_id):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Success Task Begin")
        mailer = Mailer([user.user.email] + settings.ADMIN_EMAILS)
        mailer.challenge_passed(user, challenge,)

        message = (
            f"Congratulations! You just hit your {challenge.profit_target_percent}% profit target. "
            f"Your funded account credentials will be sent within the next 24-48hrs."
        )
        with transaction.atomic():
            Notification.objects.create(
                recipient=user.user,
                sender=None,  # system-generated
                title="Profit Target Reached",
                message=message,
                url="/dashboard/performance",
                type="success",
                metadata={
                    "account_size": float(challenge.account_size),
                    "challenge_type": challenge.challenge_type,
                    "challenge_class": challenge.challenge_class
                },
            )

            ChallengeLog.objects.create(
                user=user,
                action='CHALLENGE_PASSED',
                details=f'Challenge completed',
                timestamp=now()
            )
        print("Success Task stopped")

    except Exception as err:
        traceback.print_exc()


@shared_task
def send_challenge_failed_mail_task(user_login, challenge_id, compiled_violation:List[ViolationDict]):
    try:
        print("Notification Task Begin")
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)

        reasons = [f"{reason["type"]}: {reason['message']}" for reason in compiled_violation]
        reason_text = ", ".join(reasons) if reasons else "Unspecified reasons"

        mailer = Mailer([user.user.email] + settings.ADMIN_EMAILS)
        mailer.challenge_failed(user, challenge, reasons)

        with transaction.atomic():
            Notification.objects.create(
                recipient=user.user,
                sender=None,  # system-generated
                title=f"You have failed the challenge \"{challenge.name}\"",
                message=(
                    f"Unfortunately, you failed the challenge due to the following reason(s):\n"
                    f"{reason_text}"
                ),
                url=f"/analytics/?login={user.login}",
                type="error",  # or "failure" if you add that to your choices
            )

            for violation in compiled_violation:
                vio = RuleViolationLog.objects.create(
                    login=user_login,
                    severity='critical',
                    violation_type=violation["type"],
                    message=violation["message"],
                )

            ChallengeLog.objects.create(
                user=user,
                action='CHALLENGE_FAILED',
                details=f'{reason_text}',
                timestamp=now()
            )
        print("Notification Task stopped")

    except Exception as err:
        traceback.print_exc()



@shared_task
def trade_rule_violation_alert(
    user_login, 
    compiled_violations:List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]], 
    symbol
):
    try:
        print("Violation Notification Task Begin")
        user=MT5User.objects.get(login=user_login)

        with transaction.atomic():
            for violation, severity in compiled_violations:
                vio = RuleViolationLog.objects.create(
                    login=user_login,
                    severity=severity,
                    violation_type=violation["type"],
                    message=violation["message"],
                    trade_data={"symbol": symbol}
                )
                #Send user email
                mailer = Mailer(user.user.email)
                mailer.user_trade_rule_violation(user, vio)
                #Send admin mail
                if severity == 'critical':
                    mailer = Mailer(settings.ADMIN_EMAILS)
                    mailer.admin_trade_rule_violation(user, vio)
            print("Violation Notification Task Stopped")
    except Exception as err:
        traceback.print_exc()


@shared_task
def account_rule_violation_log(
    user_login, 
    compiled_violations:List[Tuple[ViolationDict, Literal['warning', 'severe', 'critical']]], 
):
    try:
        print("Account Rule Violation Log Task Begin")
        with transaction.atomic():
            for violation, severity in compiled_violations:
                vio = RuleViolationLog.objects.create(
                    login=user_login,
                    severity=severity,
                    violation_type=violation["type"],
                    message=violation['type'],
                    auto_closed=True
                )
                print(vio)
        print("Account Rule Violation Log Task Stopped")
    except Exception as err:
        traceback.print_exc()

@shared_task
def fail_account(login, failure_type: Literal["expired", "failed"], reasons):
    try:
        mt5_account = MT5Account.objects.get(login=login)
        print(f"Retrieved Database Account: {login}")
        mt5_account.challenge_failed = True
        mt5_account.challenge_failure_date = now()
        mt5_account.active = False
        mt5_account.failure_reason = reasons
        mt5_account.save()

        print(f"Decided failure type: {failure_type}")
        mt5_user = mt5_account.mt5_user
        mt5_user.account_status = failure_type
        mt5_user.save()
        print(f"Failed account", login)
    except Exception as err:
        print("Error failing account")
        traceback.print_exc()

@shared_task
def pass_account(login, challenge_id):
    try:        
        mt5_account = MT5Account.objects.get(login=login)
        mt5_account.challenge_completed = True
        mt5_account.challenge_completion_date = now()
        mt5_account.is_funded_eligible = True
        mt5_account.save()

        mt5_user = mt5_account.mt5_user
        mt5_user.account_status = 'challenge_passed'
        mt5_user.save()

        challenge = PropFirmChallenge.objects.get(id=challenge_id)

        if challenge.challenge_type == 'one_step':
            send_challenge_success_mail_task(login, challenge_id)
        else:
            send_phase_2_success_task(login, challenge_id)

    except Exception as err:
        print(f"Error passing account: {login}")
        traceback.print_exc()

@shared_task
def move_account_to_step_2(login):
    try:
        mt5_account = MT5Account.objects.get(login=login)
        mt5_account.step = 2
        mt5_account.phase_2_start_date = now()
        mt5_account.save()

        print(f"moved account to step 2: {login}")
    except Exception as err:
        print(f"Error moving account to step 2: {login}")
        traceback.print_exc()