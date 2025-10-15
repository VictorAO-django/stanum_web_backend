from django.core.management.base import BaseCommand
from confluent_kafka import Consumer
from django.conf import settings
import logging, pytz, json, traceback
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone
# from manager.bridge import MetaTraderBridge
from sub_manager.bridge import MetaTraderBridge
from trading.models import MT5User
from sub_manager.toDict import daily_to_dict
from stanum_web.tasks import *
from sub_manager.producer import p
import time
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
            accounts = bridge.get_account_list()
            if accounts:
                for acc in accounts:
                    daily = bridge.manager.DailyRequest(
                        acc.Login,
                        int(yesterday_start.timestamp()),
                        int(today_start.timestamp())
                    )
                    if daily:
                        print(f"Got daily report for login={acc.Login} length={len(daily)}")
                        for i in daily:
                            save_mt5_daily.delay(daily_to_dict(i))
                    else:
                        print(f"No daily report for login={acc.Login}")
        

        local_tz = pytz.timezone('Africa/Lagos')
        # Run every day at 00:15 UTC
        scheduler.add_job(fetch_daily_reports, trigger="cron", hour=0, minute=15, timezone=local_tz)
        #Run every hour
        scheduler.add_job(bridge.periodic_cleanup, trigger="cron", minute=0)
        #Run 6pm everyday
        scheduler.add_job(bridge.periodic_account_rating, trigger="cron", hour=18, minute=0, timezone=local_tz, next_run_time=datetime.now())
        scheduler.add_job(
            check_min_and_max_trading_days,
            trigger="cron",
            hour=0, minute=0,
            id="check_trading_days",
            replace_existing=True,
        )
        scheduler.add_job(
            lambda: p.produce("persist_valid_data"),
            trigger="cron",
            minute=0,
            hour="6-22",
            day_of_week="mon-fri",
            id="persist_valid_data_hourly",
            replace_existing=True,
        )
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
                traceback.print_exc()
                logger.warning("Reconnecting in 5s...")
                time.sleep(5)
