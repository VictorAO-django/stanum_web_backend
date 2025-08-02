from django.conf import settings
import requests, hmac, hashlib

class NOWPaymentsService:
    def __init__(self):
        self.api_key = settings.NOWPAYMENTS_API_KEY
        self.base_url = settings.NOWPAYMENTS_BASE_URL
        self.headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }
    
    def get_available_currencies(self):
        """Get list of available cryptocurrencies"""
        try:
            response = requests.get(f"{self.base_url}/currencies", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {'error': str(e)}
    
    def get_estimate(self, amount, currency_from='USD', currency_to='btc'):
        """Get estimated crypto amount for fiat amount"""
        try:
            params = {
                'amount': amount,
                'currency_from': currency_from,
                'currency_to': currency_to
            }
            response = requests.get(f"{self.base_url}/estimate", 
                                  params=params, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {'error': str(e)}
    
    def create_payment(self, price_amount, price_currency, pay_currency, 
                      order_id, order_description, ipn_callback_url=None):
        """Create a new payment"""
        try:
            payload = {
                'price_amount': float(price_amount),
                'price_currency': price_currency,
                'pay_currency': pay_currency,
                'order_id': order_id,
                'order_description': order_description,
            }
            
            if ipn_callback_url:
                payload['ipn_callback_url'] = ipn_callback_url
            
            response = requests.post(f"{self.base_url}/payment", 
                                   json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {'error': str(e)}
    
    def get_payment_status(self, payment_id):
        """Get payment status"""
        try:
            response = requests.get(f"{self.base_url}/payment/{payment_id}", 
                                  headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {'error': str(e)}
    
    def verify_ipn_signature(self, request_body, signature):
        """Verify IPN callback signature"""
        if not settings.NOWPAYMENTS_IPN_SECRET:
            return False
        
        expected_signature = hmac.new(
            settings.NOWPAYMENTS_IPN_SECRET.encode('utf-8'),
            request_body,
            hashlib.sha512
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)