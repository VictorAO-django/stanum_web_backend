import requests
from typing import Literal
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
    
    def end_competition(self, uuid: str):
        """
        End a competition by its unique identifier.

        Args:
            uuid (str): The UUID of the competition to end.

        Returns:
            dict: The API response or an error message if something fails.
        """
        if not uuid:
            raise ValueError("Competition UUID is required.")
        endpoint = f"end-competition/{uuid}"
        try:
            response = self.post(endpoint, {})
            return response
        except Exception as e:
            raise RuntimeError(f"Failed to end competition {uuid}: {e}")


    def update_balance(self, login, amount, operation:Literal["add", "subtract"] = "add"):
        try:
            amount = float(amount)
            if operation == "subtract":
                amount = -amount
            payload = {
                "login": login,
                "amount": amount,
            }
            response = self.post("update_balance", payload)
            return response

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid amount value: {amount!r}. Error: {e}")
        
    def return_balance(self, login, initial_balance):
        try:
            payload = {
                "login": login,
                "initial_balance": float(initial_balance),
            }
            response = self.post("return_balance", payload)
            return response

        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid initial value: {initial_balance!r}. Error: {e}")

    def fund_account(self, login):
        try:
            payload = {
                "login": login
            }
            response = self.post("fund_account", payload)
            return response

        except (ValueError, TypeError) as e:
            raise ValueError(f"Error while funding: {login!r}. Error: {e}")