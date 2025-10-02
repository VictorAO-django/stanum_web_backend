from django.core.management.base import BaseCommand
from django.conf import settings
import time, logging, pytz
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
# from manager.bridge import MetaTraderBridge
from sub_manager.bridge import MetaTraderBridge
from sub_manager.sinks.daily import save_mt5_daily
from trading.models import MT5User

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Run MT5 Manager API streaming bridge"

    def handle(self, *args, **options):
        # print(settings.METATRADER_SERVER, settings.METATRADER_LOGIN, settings.METATRADER_PASSWORD, settings.METATRADER_USERGROUP)
        bridge = MetaTraderBridge(
            address=settings.METATRADER_SERVER,
            login=settings.METATRADER_LOGIN,
            password=settings.METATRADER_PASSWORD,
            user_group=settings.METATRADER_USERGROUP,
        )

        # --- APScheduler setup ---
        scheduler = BackgroundScheduler(timezone="UTC")

        def fetch_daily_reports():
            now = datetime.now(timezone.utc)
            today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
            yesterday_start = today_start - timedelta(days=1)

            print(f"[Scheduler] Fetching dailies {yesterday_start} to {today_start}")

            logins = list(
                MT5User.objects.filter(account_status='active')
                .values_list('login', flat=True)
            )
            for login in logins:
                daily = bridge.manager.DailyRequest(
                    login,
                    int(yesterday_start.timestamp()),
                    int(today_start.timestamp())
                )
                if daily:
                    print(daily)
                    print(f"Got daily report for login={login} length={len(daily)}")
                    for i in daily:
                        save_mt5_daily(i)  # <-- call your save function
                else:
                    print(f"No daily report for login={login}")
        
        local_tz = pytz.timezone('Africa/Lagos')
        # Run every day at 00:15 UTC
        scheduler.add_job(fetch_daily_reports, trigger="cron", hour=0, minute=15, timezone=local_tz)
        #Run every hour
        scheduler.add_job(bridge.periodic_cleanup, trigger="cron", minute=0)
        #Run 6pm everyday
        job=scheduler.add_job(bridge.periodic_account_rating, trigger="cron", hour=18, minute=0, timezone=local_tz, next_run_time=datetime.now())
        scheduler.start()

        # print(f"Job scheduled. Next run at: {job.next_run_time}")
        print("APScheduler started.")

        while True:
            try:
                if bridge.connect():
                    print("Bridge running...")
                    while True:
                        time.sleep(1)  # keep alive
                else:
                    time.sleep(5)

            except Exception as e:
                print(f"Bridge crashed: {e}")

            finally:
                bridge.disconnect()
                bridge.flush()
                logger.warning("Reconnecting in 5s...")
                time.sleep(5)
