from django.core.management.base import BaseCommand
from stanum_web.tasks import * 

class Command(BaseCommand):
    help = "Run in-memory prop competition monitoring service"

    def handle(self, *args, **options):
        # === Your old script logic here ===
        self.stdout.write(self.style.SUCCESS("Starting InMemoryPropCompetitionMonitoring..."))

        # Example: if you had a class
        from sub_manager.InMemoryPropCompetitionMonitoring import InMemoryPropCompetitionMonitoring
        monitor = InMemoryPropCompetitionMonitoring()
        monitor.run()   # or whatever entry method you had

        self.stdout.write(self.style.SUCCESS("InMemoryPropCompetitionMonitoring finished."))
