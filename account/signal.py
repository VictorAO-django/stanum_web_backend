from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver, Signal
from django.contrib.auth.signals import user_logged_in
from .models import *
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

logger = logging.getLogger(__name__)

@receiver(user_logged_in)
def update_last_login(sender, user, request, **kwargs):
    user.last_login = timezone.now()
    user.save()

@receiver(pre_save, sender=CustomAuthToken)
def custom_auth_token_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        now = timezone.now()
        instance.access_expires_at = now + timedelta(minutes=get_setting('ACCESS_TOKEN_LIFESPAN_MINUTES', 15))
        instance.refresh_expires_at = now + timedelta(days=get_setting('REFRESH_TOKEN_LIFESPAN_DAYS', 1))
