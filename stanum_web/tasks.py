import traceback
from django.db.models.functions import TruncDate
from asgiref.sync import async_to_sync
from django.utils.dateparse import parse_datetime
from django.db import transaction
from celery import shared_task
from django.utils.timezone import now
from utils.mailer import *
from trading.models import *
from account.models import *
from challenge.models import *
from django.conf import settings
from sub_manager.InMemoryData import *
from utils.helper import encrypt_password
from sub_manager.producer import *
from sub_manager.transformer import EnhancedJSONEncoder

def to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def to_str(value):
    return str(value) if value is not None else None

def to_epoch(dt):
    """
    Normalize MT5 datetime/timestamp values into integer Unix timestamps.
    """
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return int(dt.replace(tzinfo=timezone.utc).timestamp())
    try:
        return int(dt)
    except Exception:
        return None
    
def safe_parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value  # already datetime
    if isinstance(value, str):
        return parse_datetime(value) or None
    return None

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

        reasons = [f"{reason['type']}: {reason['message']}" for reason in compiled_violation]
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


@shared_task
def update_account_ratings(accounts_to_rate):
    """
    Updates account ratings from watermarks and stats
    accounts_to_rate: List of {'watermark': watermark_data, 'stat': stat_data}
    """
    updated_count = 0
    
    for account_data in accounts_to_rate:
        watermark_data = account_data['watermark']
        stat = account_data['stat']
        
        # Extract login from watermark data
        login = watermark_data.get('login')
        if not login:
            continue
            
        try:
            mt5_user = MT5User.objects.get(login=login)
            account_rating, created = AccountRating.objects.get_or_create(
                mt5_user=mt5_user
            )
            
            # Convert watermark strings back to Decimal
            hwm_equity = Decimal(watermark_data['hwm_equity'])
            lwm_equity = Decimal(watermark_data['lwm_equity'])
            
            # Calculate max drawdown from watermarks
            if hwm_equity > 0:
                max_drawdown = ((hwm_equity - lwm_equity) / hwm_equity) * 100
                account_rating.max_drawdown = float(max_drawdown)
            else:
                account_rating.max_drawdown = 0
            
            # Update from stats (convert if they're strings)
            profit_factor = stat['profit_factor']
            if profit_factor is not None:
                profit_factor = float(Decimal(str(profit_factor)))
            account_rating.profit_factor = profit_factor
            
            win_ratio = float(Decimal(str(stat['win_ratio'])))
            account_rating.win_rate = win_ratio
            
            # Calculate score
            pf = profit_factor if profit_factor else 0
            wr = win_ratio
            dd_penalty = float(max_drawdown) * 0.5 if hwm_equity > 0 else 0
            
            score = min((pf * 20) + (wr * 0.6) - dd_penalty, 100)
            account_rating.score = max(score, 0)
            account_rating.stars = min(int(account_rating.score / 20), 5)
            
            account_rating.save()
            updated_count += 1
            
        except (MT5User.DoesNotExist, ValueError, TypeError):
            continue
            
    return f"Updated {updated_count} account ratings"


@shared_task
def delete_deal(deal_id):
    try:
        mt5_deal = MT5Deal.objects.filter(deal=deal_id)
        if mt5_deal.exists():
            mt5_deal = mt5_deal.first()
            mt5_deal.deleted = True
            mt5_deal.save()
    except Exception as err:
        traceback.print_exc()
        print("Failed to fail deal")


@shared_task
def save_mt5_deal(deal_data: dict):
    try:
        deal, _ = MT5Deal.objects.update_or_create(
            deal=deal_data["deal"],  # unique ticket
            defaults=deal_data
        )
        return deal.deal

    except Exception:
        import traceback
        traceback.print_exc()
        print("Failed to save deal")
        return None

@shared_task
def save_position(position_data: dict):
    """Save or update MT5Position with create/update logic"""

    # Convert datetime fields back
    for field in ["time_create", "time_update", "activation_time"]:
        if position_data.get(field):
            position_data[field] = safe_parse_datetime(position_data[field]) or now() 

    mt5_position, created = MT5Position.objects.update_or_create(
        position_id=position_data["position_id"],
        defaults=position_data,
    )

    return mt5_position.position_id, created

@shared_task
def delete_position(position_id):
    try:
        pos = MT5Position.objects.filter(position_id=position_id)
        if pos.exists():
            pos = pos.first()
            pos.closed = True
            pos.save()
    except Exception as err:
        traceback.print_exc()
        print(f"Failed to delete_position {position_id}")

@shared_task
def clean_position(login):
    try:
        MT5Position.objects.filter(login=login).update(closed=True)
    except Exception as err:
        traceback.print_exc()
        print(f"Failed to clean position {login}")

@shared_task
def save_mt5_account(account_data):
    try:
        account_data["updated_at"] = parse_datetime(account_data["updated_at"])  # convert back to datetime

        account, created = MT5Account.objects.update_or_create(
            login=account_data["login"],
            defaults=account_data
        )
        return account.id

    except Exception as err:
        traceback.print_exc()
        print("Failed to save account")


@shared_task
def save_mt5_user(user_data: dict):
    """Hydrate MT5 user dict into Django MT5User model"""

    # Convert datetime fields back
    for field in ["registration", "last_access", "last_pass_change"]:
        if user_data.get(field):
            user_data[field] = parse_datetime(user_data[field])

    user, _ = MT5User.objects.update_or_create(
        login=user_data["login"],
        defaults=user_data,
    )
    return user.login

@shared_task
def save_mt5_daily(daily_data):
    print(daily_data)
    def convert_time(epoch):
        return datetime.fromtimestamp(epoch, tz=timezone.utc) if epoch else None
    try:
        daily_data["datetime"] = convert_time(daily_data["datetime"])  # convert back to datetime
        daily_data["datetime_prev"] = convert_time(daily_data["datetime_prev"]) # convert back to datetime
        daily, _ = MT5Daily.objects.update_or_create(
            login=daily_data["login"],
            datetime=daily_data["datetime"],
            defaults=daily_data
        )
        return daily.id

    except Exception as err:
        traceback.print_exc()
        print("Failed to save daily")

@shared_task
def delete_user(login):
    try:
        MT5User.objects.filter(login=login).delete()
        MT5Position.objects.filter(login=login).delete()
        MT5Deal.objects.filter(login=login).delete()
    except Exception as err:
        traceback.print_exc()
        print("Failed to delete user")

@shared_task
def user_login(ip:str, user, type):
    try:
        mt_user = MT5User.objects.get(login=user.Login)
        MT5UserLoginHistory.objects.create(mt_user=mt_user, action='login', ip=ip, type=type)
    except Exception as err:
        traceback.print_exc()
        print("Failed to save user Login History")

@shared_task
def user_logout(ip:str, user, type):
    try:
        mt_user = MT5User.objects.get(login=user.Login)
        MT5UserLoginHistory.objects.create(mt_user=mt_user, action='logout', ip=ip, type=type)
    except Exception as err:
        traceback.print_exc()
        print("Failed to save user Logout History")

@shared_task
def change_password(login, password):
    try:
        mt5_user = MT5User.objects.get(login=login)
        mt5_user.password = encrypt_password(password)
        mt5_user.save(update_fields=["password"])
    except Exception as err:
        traceback.print_exc()
        print("Failed to change user password")



@shared_task
def persist_competition_results_task(competition_uuid: str, participants_data: list):
    """
    Background task to persist competition results to database
    Called by rule engine after receiving Kafka finalize signal
    """
    try:
        print(f"Persisting {len(participants_data)} results for competition {competition_uuid}")
        try:
            ctx = Competition.objects.get(uuid=competition_uuid)
            ctx.ended = True
            ctx.ended_at= datetime.now(timezone.utc)
            ctx.save()
        except:
            traceback.print()

        results_created = 0
        for result_data in participants_data:
            CompetitionResult.objects.update_or_create(
                competition_uuid=competition_uuid,
                login=result_data["login"],
                defaults={
                    "rank": result_data["rank"],
                    "username": result_data["username"],
                    "starting_balance": result_data["starting_balance"],
                    "final_equity": result_data["final_equity"],
                    "profit": result_data["profit"],
                    "return_percent": result_data["return_percent"],
                    "max_drawdown": result_data["max_drawdown"],
                    "total_trades": result_data["total_trades"],
                    "winning_trades": result_data["winning_trades"],
                    "win_rate": result_data["win_rate"],
                    "score": result_data["score"],
                    "finalized_at": datetime.now(timezone.utc)
                }
            )
            results_created += 1
        
        print(f"Successfully persisted {results_created} results for competition {competition_uuid}")
        
        return {
            "success": True,
            "competition_uuid": competition_uuid,
            "results_saved": results_created
        }
        
    except Exception as e:
        traceback.print_exc()
        print(f"Error persisting competition results: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }
    

@shared_task
def check_min_and_max_trading_days():
    today = now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    users = (
        MT5User.objects
        .exclude(challenge=None)
        .filter(funded=False, account_status='active')
    )

    for user in users:
        try:
            challenge = user.challenge
            max_days = challenge.max_trading_days or 0
            additional_days = challenge.additional_trading_days or 0
            total_allowed_days = max_days + additional_days

            account_created_at = user.created_at.date()
            days_elapsed = (today - account_created_at).days

            # 🔸 MAX TRADING DAYS CHECK
            if days_elapsed >= total_allowed_days:
                with transaction.atomic():
                    user.account_status = 'expired'
                    user.save(update_fields=['account_status'])

                    violation = [
                        {"type": "MAX_DAYS_EXCEEDED", "message": f"{days_elapsed} > allowed {total_allowed_days}"}
                    ]
                    mt5_account = MT5Account.objects.filter(login=user.login).first()
                    if mt5_account:
                        mt5_account.challenge_failed = True
                        mt5_account.challenge_failure_date = now()
                        mt5_account.active = False
                        mt5_account.failure_reason = violation
                        mt5_account.save()

                    data = {
                        "login": user.login,
                        "broken_rules": violation
                    }
                    p.produce(
                        "accounts.fail", 
                        json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
                    )
                continue

            # 🔸 WEEKLY MINIMUM TRADING DAYS CHECK (only run on Sundays)
            if today.weekday() == 6:
                weekly_days = (
                    MT5Position.objects.filter(
                        login=user.login,
                        time_create__date__range=(start_of_week, end_of_week)
                    )
                    .annotate(day=TruncDate('time_create'))
                    .values('day')
                    .distinct()
                    .count()
                )

                if weekly_days < (challenge.min_trading_days or 0):
                    with transaction.atomic():
                        user.account_status = 'failed'
                        user.save(update_fields=['account_status'])
                        
                        violation = [
                            {"type": "WEEKLY_TRADING_DAYS_NOT_MET", "message": f"Traded {weekly_days} < required {challenge.min_trading_days}"}
                        ]
                        mt5_account = MT5Account.objects.filter(login=user.login).first()
                        if mt5_account:
                            mt5_account.challenge_failed = True
                            mt5_account.challenge_failure_date = now()
                            mt5_account.active = False
                            mt5_account.failure_reason = violation
                            mt5_account.save()

                        data = {
                            "login": user.login,
                            "broken_rules": violation
                        }
                        p.produce(
                            "accounts.fail", 
                            json.dumps(data, cls=EnhancedJSONEncoder).encode("utf-8")
                        )
        except Exception:
            p.flush()
            traceback.print_exc()



@shared_task
def process_drawdowns_task(serialized_json: str):
    """
    Process serialized daily drawdown data and upsert into AccountDrawdown table.
    """
    data = json.loads(serialized_json)
    print("DAILY DRAWDOWN", data)
    # Loop through all accounts and their daily drawdown data
    for login, daily_map in data.items():
        for day_str, dd in daily_map.items():
            try:
                drawdown_date = date.fromisoformat(dd["date"])
                equity_high = Decimal(str(dd["equity_high"]))
                equity_low = Decimal(str(dd["equity_low"]))
                drawdown_percent = Decimal(str(dd["drawdown_percent"]))

                # Upsert logic — update if exists, otherwise create new record
                with transaction.atomic():
                    obj, created = AccountDrawdown.objects.update_or_create(
                        login=login,
                        date=drawdown_date,
                        defaults={
                            "equity_high": equity_high,
                            "equity_low": equity_low,
                            "drawdown_percent": drawdown_percent,
                        },
                    )

                    # Optional: print or log for debugging
                    action = "Created" if created else "Updated"
                    print(f"[{action}] {login} {drawdown_date} → DD {drawdown_percent}%")

            except Exception as e:
                # Avoid breaking entire loop if one record fails
                traceback.print_exc()
                continue


@shared_task
def process_total_drawdowns_task(serialized_json: str):
    """
    Upsert AccountTotalDrawdown records from serialized dataclass dict.
    """
    data = json.loads(serialized_json)

    for login, dd in data.items():
        try:
            with transaction.atomic():
                obj, created = AccountTotalDrawdown.objects.update_or_create(
                    login=login,
                    defaults={
                        "equity_peak": Decimal(str(dd["equity_peak"])),
                        "equity_low": Decimal(str(dd["equity_low"])),
                        "drawdown_percent": Decimal(str(dd["drawdown_percent"])),
                    },
                )
                action = "Created" if created else "Updated"
                print(f"[{action}] Total drawdown → {login}: {obj.drawdown_percent}%")
        except Exception:
            traceback.print_exc()
            continue



@shared_task
def process_account_watermarks_task(serialized_json: str):
    """
    Upsert AccountWatermarks records from serialized dataclass dict.
    """
    data = json.loads(serialized_json)
    for login, wm in data.items():
        try:
            with transaction.atomic():
                obj, created = AccountWatermarks.objects.update_or_create(
                    login=login,
                    defaults={
                        "hwm_balance": Decimal(str(wm["hwm_balance"])),
                        "hwm_equity": Decimal(str(wm["hwm_equity"])),
                        "lwm_balance": Decimal(str(wm["lwm_balance"])),
                        "lwm_equity": Decimal(str(wm["lwm_equity"])),
                        # "hwm_date": datetime.fromisoformat(wm["hwm_date"]),
                        # "lwm_date": datetime.fromisoformat(wm["lwm_date"]),
                    },
                )
                action = "Created" if created else "Updated"
                print(f"[{action}] Watermark → {login}")
        except Exception:
            traceback.print_exc()
            continue