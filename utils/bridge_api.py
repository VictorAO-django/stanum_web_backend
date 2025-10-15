import requests
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class BridgeApi:
    def __init__(self):
        self.base_url = settings.BRIDGE_URL.rstrip("/")
        self.headers = {
            "X-BRIDGE-SECRET": settings.BRIDGE_SECRET,
            "Content-Type": "application/json",
        }
        
    def post(self, endpoint: str, data: dict):
        """Send POST request to the bridge service."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"  # respect dynamic endpoint
        try:
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            response.raise_for_status()
            logger.info(f"[BridgeApi] POST {url} succeeded with status {response.status_code}")
            return response.json()  # or True if you just care about success
        except requests.exceptions.HTTPError as e:
            logger.error(f"[BridgeApi] HTTP error: {e.response.status_code} {e.response.text}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[BridgeApi] Request failed: {e}")
        return None