import traceback
from celery import shared_task
from django.utils.timezone import now
from utils.mailer import *
from .models import *
from account.models import *
from challenge.models import *

@shared_task
def send_phase_1_success_task(user_login, challenge_id,):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Phase 1 Notification Task Begin")
        mailer = Mailer(user.user.email)
        mailer.challenge_passed_1(user, challenge)

        message = (
            f"Congratulations! You just hit your {challenge.profit_target_percent}% profit target. "
            f"This marks the Phase 1 of the challenge as successful. "
            f"You can now proceed to phase 2."
        )

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


@shared_task
def send_phase_2_success_task(user_login, challenge_id,):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Phase 2 Notification Task Begin")
        mailer = Mailer(user.user.email)
        mailer.challenge_passed_1(user, challenge)

        message = (
            f"Congratulations! You just hit your {challenge.phase_2_profit_target_percent}% profit target. "
            f"This marks the challenge as successful. "
            f"Your funded account credentials will be sent within the next 24-48hrs"
        )

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

@shared_task
def send_challenge_success_mail_task(user_login, challenge_id):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Success Task Begin")
        mailer = Mailer(user.user.email)
        mailer.challenge_passed(user, challenge,)

        message = (
            f"Congratulations! You just hit your {challenge.profit_target_percent}% profit target. "
            f"Your funded account credentials will be sent within the next 24-48hrs."
        )
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
def send_challenge_failed_mail_task(user_login, challenge_id, failure_reasons):
    try:
        user=MT5User.objects.get(login=user_login)
        challenge=PropFirmChallenge.objects.get(id=challenge_id)
        print("Notification Task Begin")
        mailer = Mailer(user.user.email)
        mailer.challenge_failed(user, challenge, failure_reasons)

        reason_text = ", ".join(failure_reasons) if failure_reasons else "Unspecified reasons"
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

        ChallengeLog.objects.create(
            user=user,
            action='CHALLENGE_FAILED',
            details=f', '.join(failure_reasons),
            timestamp=now()
        )
        print("Notification Task stopped")

    except Exception as err:
        traceback.print_exc()