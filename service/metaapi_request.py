import requests
from typing import Dict, Any
from django.conf import settings
from metaapi_cloud_sdk import MetaApi
import logging

logger = logging.getLogger(__name__)


class MetaApiRequestError(Exception):
    """Custom exception for MetaApi request errors"""
    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class MetaApiRequest:
    """
    Django helper class to access FastAPI PropFirm MT4/MT5 Manager API endpoints
    """
    
    def __init__(self, base_url: str = None, timeout: int = 30):
        self.base_url = base_url or getattr(settings, 'FASTAPI_BASE_URL', 'http://localhost:8001')
        self.timeout = timeout
        self.base_url = self.base_url.rstrip('/')
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to FastAPI"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                timeout=self.timeout,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            try:
                error_data = response.json()
                detail = error_data.get('detail', 'Unknown error')
            except:
                detail = response.text
            
            raise MetaApiRequestError(
                message=f"HTTP {response.status_code}: {detail}",
                status_code=response.status_code
            )
        except requests.exceptions.RequestException as e:
            raise MetaApiRequestError(f"Request failed: {str(e)}")
    
    def health_check(self) -> Dict[str, Any]:
        """Health check endpoint"""
        return self._request('GET', '/health')
    
    def get_accounts(self) -> Dict[str, Any]:
        """Get all managed accounts"""
        return self._request('GET', '/accounts')
    
    def disable_account(self, account_id: str, reason: str = "Manual disable") -> Dict[str, Any]:
        """Disable a trading account"""
        return self._request('POST', f'/accounts/{account_id}/disable', params={'reason': reason})
    
    def close_positions(self, account_id: str) -> Dict[str, Any]:
        """Close all positions for an account"""
        return self._request('POST', f'/accounts/{account_id}/close-positions')
    
    def discover_accounts(self) -> Dict[str, Any]:
        """Manually trigger account discovery"""
        return self._request('POST', '/accounts/discover')
    
    def connect_account(self, account_id: str) -> Dict[str, Any]:
        """Manually connect a specific account"""
        return self._request('POST', f'/accounts/{account_id}/connect')
    
    def disconnect_account(self, account_id: str, reason: str = "Manual disconnect") -> Dict[str, Any]:
        """Manually disconnect a specific account"""
        return self._request('POST', f'/accounts/{account_id}/disconnect', params={'reason': reason})
    
    def get_connection_status(self, account_id: str) -> Dict[str, Any]:
        """Get detailed connection status for an account"""
        return self._request('GET', f'/accounts/{account_id}/connection-status')
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        return self._request('GET', '/system/stats')
    
    def get_account_stats(self, account_id: str) -> Dict[str, Any]:
        """Get account statistics"""
        return self._request('GET', f'/accounts/{account_id}/stats')
    
    

async def create_account():
    try:
        api = MetaApi(settings.METAAPI_TOKEN)
        account = await api.metatrader_account_api.create_account(account={
            'name': 'Trading account #1',
            'type': 'cloud',
            'login': '1234567',
            'platform': 'mt5',
            # password can be investor password for read-only access
            'password': 'qwerty',
            'server': 'ICMarketsSC-Demo',
            'magic': 123456,
            'keywords': ["Raw Trading Ltd"],
            'quoteStreamingIntervalInSeconds': 2.5, # set to 0 to receive quote per tick
            'reliability': 'high' # set this field to 'high' value if you want to increase uptime of your account (recommended for production environments)
        })
        return account
    
    except Exception as err:
        # process errors
        if hasattr(err, 'details'):
            # returned if the server file for the specified server name has not been found
            # recommended to check the server name or create the account using a provisioning profile
            if err.details == 'E_SRV_NOT_FOUND':
                print(err)
            # returned if the server has failed to connect to the broker using your credentials
            # recommended to check your login and password
            elif err.details == 'E_AUTH':
                print(err)
            # returned if the server has failed to detect the broker settings
            # recommended to try again later or create the account using a provisioning profile
            elif err.details == 'E_SERVER_TIMEZONE':
                print(err)