
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'stanum_web.settings')

app = Celery('stanum_web')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.broker_connection_retry_on_startup = True

# Force-load tasks from settings module
app.autodiscover_tasks(['stanum_web'])
