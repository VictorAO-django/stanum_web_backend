from django.core.management.base import BaseCommand
from stanum_web.tasks import * 

class Command(BaseCommand):
    help = "Run in-memory prop monitoring service"

    def handle(self, *args, **options):
        # === Your old script logic here ===
        self.stdout.write(self.style.SUCCESS("Starting InMemoryPropMonitoring..."))

        # Example: if you had a class
        from sub_manager.InMemoryPropMonitoring import InMemoryPropMonitoring
        monitor = InMemoryPropMonitoring()
        monitor.run()   # or whatever entry method you had

        self.stdout.write(self.style.SUCCESS("InMemoryPropMonitoring finished."))
