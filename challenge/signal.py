from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver, Signal
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from .models import *
from django.utils import timezone


@receiver(pre_save, sender=PropFirmChallenge)
def updated_pre_save(sender, instance, **kwargs):
    now = timezone.now()
    instance.updated_at = now
