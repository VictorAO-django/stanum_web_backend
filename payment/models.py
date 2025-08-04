from django.db import models
from django.contrib.auth import get_user_model
import uuid
User = get_user_model()

class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('waiting', 'Waiting'),
        ('confirming', 'Confirming'),
        ('confirmed', 'Confirmed'),
        ('sending', 'Sending'),
        ('partially_paid', 'Partially Paid'),
        ('finished', 'Finished'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('expired', 'Expired'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    order_id = models.CharField(max_length=100, unique=True)
    order_description = models.TextField()
    price_amount = models.DecimalField(max_digits=20, decimal_places=8)
    price_currency = models.CharField(max_length=10, default='USD')
    pay_currency = models.CharField(max_length=10)
    pay_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    pay_address = models.CharField(max_length=255, null=True, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='waiting')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Payment {self.order_id} - {self.payment_status}"



class Transaction(models.Model):
    PAYMENT_METHODS = [
        ('card', 'Card'),
        ('bank', 'Bank'),
        ('apple_pay', 'Apple Pay'),
        ('ussd', 'USSD'),
        ('qr', 'QR Code'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Bank Transfer'),
        ('eft', 'EFT'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('abandoned', 'Abandoned'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    paystack_reference = models.CharField(max_length=100, blank=True, null=True)
    authorization_url = models.URLField(blank=True, null=True)
    access_code = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.reference} - {self.amount} {self.currency}"