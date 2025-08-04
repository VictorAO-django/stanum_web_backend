
import requests
import json
from django.conf import settings
from decimal import Decimal

class PaystackService:
    def __init__(self):
        self.secret_key = settings.PAYSTACK_SECRET_KEY
        self.public_key = settings.PAYSTACK_PUBLIC_KEY
        self.base_url = settings.PAYSTACK_BASE_URL
        self.headers = {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }
    
    def initialize_transaction(self, email, amount, reference, payment_method=None, callback_url=None, metadata=None):
        """Initialize a Paystack transaction with specific payment method"""
        url = f"{self.base_url}/transaction/initialize"
        
        # Convert amount to kobo (smallest currency unit)
        amount_in_kobo = int(amount * 100)
        
        payload = {
            'email': email,
            'amount': amount_in_kobo,
            'reference': reference,
            'currency': 'NGN',
        }
        
        if callback_url:
            payload['callback_url'] = callback_url
        
        if metadata:
            payload['metadata'] = metadata
        
        # Add specific payment method channels
        if payment_method:
            payload['channels'] = [payment_method]
        
        try:
            response = requests.post(url, headers=self.headers, data=json.dumps(payload))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'status': False, 'message': str(e)}
    
    def verify_transaction(self, reference):
        """Verify a transaction status"""
        url = f"{self.base_url}/transaction/verify/{reference}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'status': False, 'message': str(e)}