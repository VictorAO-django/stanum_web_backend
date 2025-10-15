from django.core.management.base import BaseCommand
from stanum_web.tasks import * 
import sys

class Command(BaseCommand):
    help = "Run in-memory prop monitoring service"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting InMemoryPropMonitoring..."))

        from sub_manager.InMemoryBridgeAdmin import MetaTraderBridge
        monitor = MetaTraderBridge()

        def shutdown(signum, frame):
            self.stdout.write(self.style.WARNING("Shutting down service..."))
            monitor.stop()  # optional custom cleanup
            sys.exit(0)

        monitor.run()  # main loop
