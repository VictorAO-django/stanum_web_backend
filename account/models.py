from django.db import models
from django.contrib.auth.models import AbstractUser, AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from uuid import uuid4
from django.contrib.postgres.fields import ArrayField, JSONField 
import datetime, secrets
from datetime import timedelta

def generate_token():
    return secrets.token_hex(32)  # 64-char string

def get_setting(name, default):
    return getattr(settings, 'CUSTOM_AUTH', {}).get(name, default)

class CustomAuthToken(models.Model):
    access_token = models.CharField(max_length=64, unique=True, default=generate_token)
    refresh_token = models.CharField(max_length=64, unique=True, default=generate_token)

    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()

    # Generic relation to the user-like object
    user_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    user_id = models.PositiveIntegerField()
    user = GenericForeignKey('user_type', 'user_id')

    created = models.DateTimeField(auto_now_add=True)

    def has_access_expired(self):
        return timezone.now() >= self.access_expires_at

    def has_refresh_expired(self):
        return timezone.now() >= self.refresh_expires_at
    
    def rotate_access_token(self):
        self.access_token = generate_token()
        self.access_expires_at = timezone.now() + timedelta(
            minutes=get_setting('ACCESS_TOKEN_LIFESPAN_MINUTES', 15)
        )
        self.save()

    def refresh(self):
        self.access_token = generate_token()
        self.refresh_token = generate_token()
        self.access_expires_at = timezone.now() + timedelta(minutes=get_setting('ACCESS_TOKEN_LIFESPAN_MINUTES', 15))
        self.refresh_expires_at = timezone.now() + timedelta(days=get_setting('REFRESH_TOKEN_LIFESPAN_DAYS', 1))
        self.save()
        return self

class UserManager(BaseUserManager):
    def create_user(self, email, password, **other_fields):
        email = self.normalize_email(email)
        if not other_fields.get("username"):
            other_fields["username"] = str(uuid4())[:30]  # generate unique username

        user = self.model(
            email=email,
            **other_fields
        )
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **other_fields):
        user = self.create_user(
            email = self.normalize_email(email),
            password=password,
            **other_fields
        )
        user.email_verified = True
        user.is_admin = True
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user
    

class User(AbstractUser):
    email = models.EmailField(blank=False, unique=True)
    username = models.CharField(blank=True, null=True, max_length=255)
    email_verified = models.BooleanField(default=False)
    has_accepted_terms = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    lock_count = models.PositiveIntegerField(default=0)
    lock_duration = models.DateTimeField(blank=True, null=True)
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return f'{self.email}'
    
    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'
    
    def is_locked(self):
        now = timezone.now()
        if self.lock_duration:
            if self.lock_duration <= now:
                return False
            return True
        return False    

class MT5Account(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account_number = models.CharField(max_length=50)  # MT5 login/account number
    password = models.CharField(max_length=100)       # Use encryption in production
    server = models.CharField(max_length=100)         # e.g., ICMarketsSC-Live03
    account_id = models.CharField(max_length=100, blank=True, null=True)  # MetaApi ID
    created_at = models.DateTimeField(auto_now_add=True)

    current = models.BooleanField(default=True, blank=True, null=True)

    name = models.CharField(max_length=255, blank=True, null=True)
    broker = models.CharField(max_length=255, blank=True, null=True)
    platform = models.CharField(max_length=10, blank=True, null=True)  # e.g. 'mt5'
    type = models.CharField(max_length=50, blank=True, null=True)  # e.g. 'ACCOUNT_TRADE_MODE_DEMO'
    currency = models.CharField(max_length=10, blank=True, null=True)
    balance = models.FloatField(default=0)
    equity = models.FloatField(default=0)
    margin = models.FloatField(default=0)
    free_margin = models.FloatField(default=0)
    leverage = models.IntegerField(default=0)
    margin_level = models.FloatField(null=True, blank=True)
    credit = models.FloatField(default=0)
    trade_allowed = models.BooleanField(default=False)
    investor_mode = models.BooleanField(default=False)
    margin_mode = models.CharField(max_length=100, blank=True, null=True)
    account_currency_exchange_rate = models.FloatField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.account_number} - {self.account_id}"
    

class OTP(models.Model):
    EVENT_CHOICES = (
        ('registration', 'Registration'),
        ('password_reset', 'Password Reset'),
    )

    # Generic foreign key to allow linking to either Seller or Buyer or other models
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    user = GenericForeignKey('content_type', 'object_id')

    otp_code = models.CharField(max_length=4)
    event = models.CharField(choices=EVENT_CHOICES, max_length=50)  # Type of event that triggered OTP
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # OTP expiry time
    is_used = models.BooleanField(default=False)
    otp_id = models.UUIDField(default=uuid4, unique=True, editable=False)

    def save(self, *args, **kwargs):
        # Set expiry time to 5 minutes from now if not already set
        if not self.expires_at:
            self.expires_at = timezone.now() + datetime.timedelta(minutes=5)
        super().save(*args, **kwargs)

    def has_expired(self):
        """Check if the OTP has expired."""
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"OTP for {self.user} - {self.event}"
# Create your models here.
