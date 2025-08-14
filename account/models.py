from django.db import models
from django.contrib.auth.models import AbstractUser, AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from django.conf import settings
from django.core.validators import RegexValidator
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from uuid import uuid4
from django.contrib.postgres.fields import ArrayField, JSONField 
import datetime, secrets
from datetime import timedelta
import uuid, pyotp
from django.utils.crypto import get_random_string

phone_validator = RegexValidator(
    regex=r'^\+\d{6,15}$',
    message="Phone number must be entered in the format: +234xxxxxxxxxx. Up to 15 digits allowed."
)

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
    full_name = models.CharField(blank=False, max_length=255)
    username = models.CharField(blank=True, null=True, max_length=255)
    date_of_birth = models.CharField(max_length=255, blank=False)
    phone_number = models.CharField(
        max_length=16,
        unique=True,
        null=True,
        validators=[phone_validator],
        help_text="Enter your Number in international format, e.g. +234XXXXXXXXXX",
        error_messages={
            'unique': 'This phone number is already registered',
            'required': 'We need your phone to onboard you.'
        }
    )
    country = models.CharField(max_length=255, blank=False)

    email_verified = models.BooleanField(default=False)
    has_accepted_terms = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    otp_secret = models.CharField(max_length=32, blank=True, null=True)
    is_2fa_enabled = models.BooleanField(default=False)

    lock_count = models.PositiveIntegerField(default=0)
    lock_duration = models.DateTimeField(blank=True, null=True)
    
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return f'{self.email}'
    
    def is_locked(self):
        now = timezone.now()
        if self.lock_duration:
            if self.lock_duration <= now:
                return False
            return True
        return False    
    

class OTP(models.Model):
    EVENT_CHOICES = (
        ('registration', 'Registration'),
        ('password_reset', 'Password Reset'),
    )

    # Generic foreign key to allow linking to either Seller or Buyer or other models
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    user = GenericForeignKey('content_type', 'object_id')

    otp_code = models.CharField(max_length=6)
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


class LoginHistory(models.Model):
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
    ]

    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    ip_address = models.GenericIPAddressField()
    browser = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        user_display = self.user.email if self.user else "Unknown User"
        return f"{user_display} - {self.action} - {self.status} @ {self.timestamp}"


def generate_referral_code():
    return get_random_string(12).upper()

class Referral(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="referral_profile")
    code = models.CharField(max_length=12, unique=True, default=generate_referral_code)
    referred_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals_made"
    )
    reward_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_referral_link(self):
        return f"{settings.FRONTEND_BASE_URL}signup?rf={self.code}"

    def __str__(self):
        return f"{self.user.username} - {self.code}"


class ReferralEarning(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="wallet")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateField(auto_now_add=True)

    def deposit(self, value):
        self.amount += value
        self.save()

    def withdraw(self, value):
        if self.amount >= value:
            self.amount -= value
            self.save()
            return True
        return False

    def __str__(self):
        return f"{self.user.username} - Balance: {self.amount}"


class ReferalEarningTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="transactions")
    transaction_type = models.CharField(max_length=6, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type.title()} - {self.amount} for {self.user.username}"


class Address(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    home_address = models.TextField(blank=True, null=True)
    town = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=False)
    zip_code = models.CharField(max_length=255, blank=True, null=False)

    home_address2 = models.TextField(blank=True, null=True)
    town2 = models.CharField(max_length=255, blank=True, null=True)
    state2 = models.CharField(max_length=255, blank=True, null=False)
    zip_code2 = models.CharField(max_length=255, blank=True, null=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.full_name} Address"


class DocumentType(models.Model):
    TYPE_CHOICES = (
        ('identity', 'Identity'),
        ('address', 'Address'),
    )
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    name = models.CharField(max_length=100)  # e.g. Passport, Driver's License
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.get_type_display()} - {self.name}"

class ProofOfIdentity(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    document_number = models.CharField(max_length=100, blank=True, null=True)
    document_file_front = models.FileField(upload_to='static/kyc/identity/')
    document_file_back = models.FileField(upload_to='static/kyc/identity/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.document_type}"


class ProofOfAddress(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    ADDRESS = [
        ('home_address_1', "Home Address 1"),
        ('home_address_2', "Home Address 2")
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    address_type = models.CharField(choices=ADDRESS, max_length=20)
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    document_file = models.FileField(upload_to='static/kyc/address/')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user} - {self.document_type}"