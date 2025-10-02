from trading.models import MT5User, RuleViolationLog
from datetime import datetime

def trigger_account_closure(mt5_login, violations):
    """Handle critical violations - close account trading"""
    try:
        # Update challenge account status
        challenge_account = MT5User.objects.get(mt5_account_id=str(mt5_login))
        challenge_account.status = 'failed'
        challenge_account.ended_at = datetime.now()
        challenge_account.save()
        
        # Log to violations table
        RuleViolationLog.objects.create(
            account=challenge_account,
            violation_type='MULTIPLE_CRITICAL',
            severity='critical',
            message=f"Account failed due to: {', '.join(violations)}",
            auto_closed=True
        )
        
        # TODO: Send alerts/notifications
        send_violation_alert(challenge_account, violations)
        
        # TODO: Disable trading on MT5 account
        # You'll need to implement this via MT5 Manager API
        # self.manager.UserUpdate(user_with_disabled_trading)
        
    except Exception as e:
        print(f"Error handling account closure: {e}")


def send_violation_alert(challenge_account: MT5User , violations):
    """Send violation alerts to trader and admins"""
    # Implement email/SMS/dashboard notifications
    print(f"Sending violation alert for account {challenge_account.login}")
    pass
