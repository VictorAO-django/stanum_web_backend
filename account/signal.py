from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver, Signal
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from .models import *
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging
from typing import Any
from utils.helper import *

User = get_user_model()
logger = logging.getLogger(__name__)

@receiver(user_logged_in)
def update_last_login(sender, user, request, **kwargs):
    user.last_login = timezone.now()
    user.save()

    LoginHistory.objects.create(
        user=user,
        action='login',
        status='success',
        ip_address=get_client_ip(request),
        browser=get_browser_info(request)
    )

@receiver(user_logged_out)
def log_user_logout(sender, request, user, **kwargs):
    LoginHistory.objects.create(
        user=user,
        action='logout',
        status='success',
        ip_address=get_client_ip(request),
        browser=get_browser_info(request)
    )

@receiver(user_login_failed)
def log_login_failed(sender: Any, credentials: dict[str, Any], request: Any, **kwargs: Any) -> None:
    attempted_identifier = credentials.get('email') 
    user = None
    try:
        user = User.objects.filter(email=attempted_identifier).first()
    except Exception:
        pass 

    LoginHistory.objects.create(
        user=user,
        action='login',
        status='failed',
        ip_address=get_client_ip(request),
        browser=get_browser_info(request)
    )

@receiver(pre_save, sender=CustomAuthToken)
def custom_auth_token_pre_save(sender, instance, **kwargs):
    if not instance.pk:
        now = timezone.now()
        instance.access_expires_at = now + timedelta(minutes=get_setting('ACCESS_TOKEN_LIFESPAN_MINUTES', 15))
        instance.refresh_expires_at = now + timedelta(days=get_setting('REFRESH_TOKEN_LIFESPAN_DAYS', 1))

