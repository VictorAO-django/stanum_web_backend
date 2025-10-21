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


class PropFirmWallet(models.Model):
    user = models.OneToOneField( User, on_delete=models.CASCADE, related_name="propfirm_wallet")
    wallet_id = models.CharField(max_length=20, unique=True, editable=False)
    currency_id=models.CharField(max_length=50, blank=True, null=True)
    pay_currency = models.CharField(max_length=10, help_text="e.g. USDT, BTC, ETH", null=True, blank=True)
    pay_network = models.CharField(max_length=10, null=True, blank=True)
    pay_address = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.wallet_id:
            self.wallet_id = f"#{uuid.uuid4().int % 1000000:06d}"  # e.g. #365435
        super().save(*args, **kwargs)


class PropFirmWalletTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("disbursed", "Disbursed"),
        #For credit
        ('failed', 'Failed'),
        ("completed", "Completed"),
    ]

    CRYPTO_NETWORK_CHOICES = [
        ("BTC", "Bitcoin"),
        ("ETH", "Ethereum ERC20"),
        ("TRX", "Tron TRC20"),
        ("BSC", "Binance Smart Chain BEP20"),
        ("SOL", "Solana"),
        ("OTHER", "Other"),
    ]

    TYPE_CHOICES = [
        ('credit', "Credit"),
        ('debit', "Debit")
    ]

    wallet = models.ForeignKey(PropFirmWallet, on_delete=models.CASCADE, related_name="transactions")
    login = models.CharField(max_length=255, null=True)
    transaction_id = models.CharField(max_length=20, unique=True, editable=False)
    type = models.CharField(choices=TYPE_CHOICES, max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    note = models.TextField(blank=True, null=True)

    # Crypto payout fields
    price_amount = models.DecimalField(max_digits=20, decimal_places=8, default=0.0)
    price_currency = models.CharField(max_length=10, default='USD')
    pay_amount = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency_id = models.CharField(max_length=255, blank=True, null=True)
    pay_currency = models.CharField(max_length=10, help_text="e.g. USDT, BTC, ETH", null=True, blank=True)
    pay_network = models.CharField(max_length=10, choices=CRYPTO_NETWORK_CHOICES, null=True, blank=True)
    pay_address = models.CharField(max_length=255, null=True, blank=True)
    payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    order_description = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = f"#TX-{uuid.uuid4().int % 1000000:06d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transaction_id} - {self.status} - {self.price_amount}"
    

def generate_withdrawal_id():
    return f"WD-{uuid.uuid4().hex[:8].upper()}"
class WithdrawalRequest(models.Model):
    STATUS=(
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )
    login=models.BigIntegerField()
    withdrawal_id = models.CharField(max_length=20, unique=True, default=generate_withdrawal_id, editable=False)
    status=models.CharField(choices=STATUS, default="pending")
    rejected_reasons=models.TextField(blank=True, null=True)
    disbursed_amount=models.DecimalField(decimal_places=2, max_digits=12, blank=True, null=True)
    currency_id=models.CharField(max_length=50, blank=True, null=True)
    pay_currency = models.CharField(max_length=10, help_text="e.g. USDT, BTC, ETH", null=True, blank=True)
    pay_network = models.CharField(max_length=10, null=True, blank=True)
    pay_address = models.CharField(max_length=255, null=True, blank=True)

    created_at=models.DateTimeField(auto_now_add=True)
    approved_at=models.DateTimeField(null=True, blank=True)
    rejected_at=models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.login} - {self.withdrawal_id} - {self.created_at} - {self.status}"