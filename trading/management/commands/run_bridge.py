from django.core.management.base import BaseCommand
from django.conf import settings
import time, logging

from manager.bridge import MetaTraderBridge

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

        while True:
            try:
                if bridge.connect():
                    logger.info("Bridge running...")
                    while True:
                        time.sleep(1)  # keep alive
                else:
                    time.sleep(5)

            except Exception as e:
                logger.exception(f"Bridge crashed: {e}")

            finally:
                bridge.disconnect()
                logger.warning("Reconnecting in 5s...")
                time.sleep(5)
