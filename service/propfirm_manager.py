import os, dotenv
import asyncio
import hashlib
import secrets
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import aiohttp
import ssl
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

dotenv.load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('propfirm_manager.log'),  # Custom path
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ChallengeStatus(Enum):
    ACTIVE = "active"
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    SUSPENDED = "suspended"

class AccountType(Enum):
    CHALLENGE = "challenge"
    FUNDED = "funded"
    DEMO = "demo"

@dataclass
class ChallengeConfig:
    """Challenge configuration parameters"""
    max_daily_loss_percent: float = 5.0
    max_total_loss_percent: float = 10.0
    profit_target_percent: float = 8.0
    minimum_trading_days: int = 4
    maximum_trading_days: int = 30
    max_lot_size: float = 1.0
    trading_start_time: str = "00:00"
    trading_end_time: str = "23:59"
    forbidden_symbols: List[str] = None

    def __post_init__(self):
        if self.forbidden_symbols is None:
            self.forbidden_symbols = []

@dataclass
class TradingAccount:
    """Trading account data structure"""
    account_id: int
    login: int
    challenge_id: str
    account_type: AccountType
    initial_balance: float
    current_balance: float
    current_equity: float
    status: ChallengeStatus
    challenge_config: ChallengeConfig
    created_at: datetime
    last_updated: datetime
    daily_losses: Dict[str, float] = None  # date -> loss amount
    total_drawdown: float = 0.0
    profit_made: float = 0.0
    trading_days: int = 0
    last_trade_time: Optional[datetime] = None

    def __post_init__(self):
        if self.daily_losses is None:
            self.daily_losses = {}

# Pydantic models for API
class CreateAccountRequest(BaseModel):
    challenge_id: str
    initial_balance: float
    challenge_config: dict
    user_id: str
    account_type: str = "challenge"

class AccountResponse(BaseModel):
    account_id: int
    login: int
    challenge_id: str
    status: str
    current_balance: float
    current_equity: float
    created_at: datetime

class ChallengeUpdateRequest(BaseModel):
    challenge_id: str
    status: Optional[str] = None
    notes: Optional[str] = None

class FinXSolClient:
    """Client for FinXSol MetaTrader Web API"""
    
    def __init__(self, server_host: str, manager_login: int, manager_password: str):
        self.server_host = server_host.replace('https://', '').replace('http://', '')
        self.manager_login = manager_login
        self.manager_password = manager_password
        self.session: Optional[aiohttp.ClientSession] = None
        self.authenticated = False
        self.password_hash = self._generate_password_hash(manager_password)
        self.base_url = None  # Will be set after finding working connection
        
    async def _test_connection(self, base_url: str) -> bool:
        """Test if a connection works"""
        try:
            if not self.session:
                timeout = aiohttp.ClientTimeout(total=10)
                # More permissive SSL settings for MetaTrader servers
                connector = aiohttp.TCPConnector(
                    ssl=False,  # Disable SSL verification
                    force_close=True,
                    enable_cleanup_closed=True
                )
                self.session = aiohttp.ClientSession(
                    timeout=timeout, 
                    connector=connector,
                    headers={'User-Agent': 'MetaTrader WebAPI Client'}
                )
            
            test_url = f"{base_url}/api/auth/start"
            params = {
                'version': '484',
                'agent': 'PropFirmManager',
                'login': str(self.manager_login),
                'type': 'manager'
            }
            
            logger.info(f"Testing connection: {test_url}")
            async with self.session.get(test_url, params=params) as response:
                response_text = await response.text()
                logger.info(f"Connection test result: {response.status} - {response_text[:200]}")
                return response.status in [200, 400, 401]  # Accept auth errors as "connected"
                
        except Exception as e:
            logger.debug(f"Connection test failed for {base_url}: {str(e)}")
            return False
    
    async def _find_working_connection(self) -> Optional[str]:
        """Try different connection methods to find working one"""
        # Common MetaTrader Web API configurations
        connection_attempts = [
            f"http://{self.server_host}:443",   # Try HTTP first (common for MT)
            f"https://{self.server_host}:443",  # Then HTTPS
            f"http://{self.server_host}:80", 
            f"http://{self.server_host}:8080",
            f"https://{self.server_host}:8443",
            f"https://{self.server_host}:8080", 
        ]
        
        logger.info("Searching for working connection...")
        for base_url in connection_attempts:
            logger.info(f"Trying: {base_url}")
            if await self._test_connection(base_url):
                logger.info(f"Found working connection: {base_url}")
                return base_url
        
        logger.error("No working connection found")
        return None
        
    def _generate_password_hash(self, password: str) -> str:
        """Generate WebAPI password hash - matches JavaScript ProcessAuth"""
        # Step 1: MD5 of password in UTF-16-LE (matches JavaScript buffer.transcode)
        password_bytes = password.encode('utf-16-le')
        md5_password = hashlib.md5(password_bytes).digest()
        
        # Step 2: MD5(password_md5 + 'WebAPI') - matches JavaScript 
        combined = md5_password + b'WebAPI'
        final_hash = hashlib.md5(combined).hexdigest()
        
        return final_hash
    
    async def authenticate(self) -> bool:
        """Authenticate with FinXSol server"""
        try:
            # First, find a working connection
            if not self.base_url:
                self.base_url = await self._find_working_connection()
                if not self.base_url:
                    logger.error("Could not establish connection to server")
                    return False
            
            if not self.session:
                timeout = aiohttp.ClientTimeout(total=30)
                connector = aiohttp.TCPConnector(
                    ssl=False,  # Disable SSL verification
                    force_close=True,
                    enable_cleanup_closed=True
                )
                self.session = aiohttp.ClientSession(
                    timeout=timeout, 
                    connector=connector,
                    headers={'User-Agent': 'MetaTrader WebAPI Client'}
                )
            
            # Step 1: Start authentication
            start_url = f"{self.base_url}/api/auth/start"
            params = {
                'version': '484',
                'agent': 'PropFirmManager',
                'login': str(self.manager_login),
                'type': 'manager'
            }
            
            logger.info(f"Attempting authentication with URL: {start_url}")
            logger.info(f"Auth params: {params}")
            
            async with self.session.get(start_url, params=params) as response:
                response_text = await response.text()
                logger.info(f"Auth start response status: {response.status}")
                logger.info(f"Auth start response: {response_text}")
                
                if response.status != 200:
                    logger.error(f"Auth start failed with status: {response.status}")
                    return False
                
                try:
                    auth_data = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response: {response_text}")
                    return False
                if auth_data.get('retcode', '').split()[0] != '0':
                    logger.error(f"Auth start error: {auth_data.get('retcode')}")
                    return False
                
                srv_rand = auth_data.get('srv_rand')
                if not srv_rand:
                    logger.error("No srv_rand received")
                    return False
            
            # Step 2: Generate client random and response
            cli_rand = secrets.token_hex(16)
            
            # Calculate srv_rand_answer
            srv_rand_bytes = bytes.fromhex(srv_rand)
            combined = bytes.fromhex(self.password_hash) + srv_rand_bytes
            srv_rand_answer = hashlib.md5(combined).hexdigest()
            
            # Step 3: Send authentication response
            answer_url = f"{self.base_url}/api/auth/answer"
            params = {
                'srv_rand_answer': srv_rand_answer,
                'cli_rand': cli_rand
            }
            
            logger.info(f"Sending auth answer to: {answer_url}")
            logger.info(f"Answer params: srv_rand_answer={srv_rand_answer}, cli_rand={cli_rand}")
            
            async with self.session.get(answer_url, params=params) as response:
                response_text = await response.text()
                logger.info(f"Auth answer response status: {response.status}")
                logger.info(f"Auth answer response: {response_text}")
                
                if response.status != 200:
                    logger.error(f"Auth answer failed with status: {response.status}")
                    return False
                
                try:
                    auth_response = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON response: {response_text}")
                    return False
                if auth_response.get('retcode', '').split()[0] != '0':
                    logger.error(f"Auth failed: {auth_response.get('retcode')}")
                    return False
                
                # Verify server response (optional but recommended)
                cli_rand_answer = auth_response.get('cli_rand_answer')
                if cli_rand_answer:
                    expected = hashlib.md5(
                        bytes.fromhex(self.password_hash) + bytes.fromhex(cli_rand)
                    ).hexdigest()
                    if cli_rand_answer != expected:
                        logger.warning("Server authentication verification failed")
                
                self.authenticated = True
                logger.info("Successfully authenticated with FinXSol server")
                return True
                
        except aiohttp.ClientError as e:
            logger.error(f"Network error during authentication: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return False
    
    async def create_account(self, balance: float, leverage: int = 100) -> Optional[Dict]:
        """Create a new trading account"""
        if not self.authenticated:
            if not await self.authenticate():
                return None
        
        # This would be the actual API call - endpoint TBD
        # Placeholder for actual implementation
        logger.info(f"Creating account with balance: {balance}, leverage: {leverage}")
        
        # Mock response - replace with actual API call
        return {
            'login': secrets.randbelow(1500) + 2500,  # Account range 2500-4000
            'password': secrets.token_hex(8),
            'investor_password': secrets.token_hex(8),
            'retcode': '0 Done'
        }
    
    async def get_account_info(self, login: int) -> Optional[Dict]:
        """Get account information"""
        if not self.authenticated:
            if not await self.authenticate():
                return None
        
        # Placeholder for actual implementation
        logger.info(f"Getting account info for: {login}")
        return {
            'login': login,
            'balance': 10000.0,
            'equity': 10000.0,
            'margin': 0.0,
            'free_margin': 10000.0
        }
    
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()

class PropFirmManager:
    """Main prop firm account manager"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.accounts: Dict[int, TradingAccount] = {}
        self.finxsol_client = FinXSolClient(
            server_host=config['server_host'],
            # port=config['port'],
            manager_login=config['manager_login'],
            manager_password=config['manager_password']
        )
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
    async def start(self):
        """Start the prop firm manager"""
        logger.info("Starting PropFirm Manager...")
        self.is_running = True
        
        # Start monitoring task
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Authenticate with FinXSol (make it optional for testing)
        if not await self.finxsol_client.authenticate():
            logger.warning("Failed to authenticate with FinXSol - continuing in offline mode")
            # Don't raise exception, continue without authentication for now
        else:
            logger.info("Successfully authenticated with FinXSol")
        
        logger.info("PropFirm Manager started successfully")
    
    async def stop(self):
        """Stop the prop firm manager"""
        logger.info("Stopping PropFirm Manager...")
        self.is_running = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        await self.finxsol_client.close()
        logger.info("PropFirm Manager stopped")
    
    async def create_trading_account(self, request: CreateAccountRequest) -> TradingAccount:
        """Create a new trading account for a challenge"""
        try:
            # Create account with FinXSol
            account_data = await self.finxsol_client.create_account(
                balance=request.initial_balance
            )
            
            if not account_data or account_data.get('retcode', '').split()[0] != '0':
                raise Exception("Failed to create account with FinXSol")
            
            # Create challenge configuration
            challenge_config = ChallengeConfig(**request.challenge_config)
            
            # Create trading account object
            account = TradingAccount(
                account_id=len(self.accounts) + 1,
                login=account_data['login'],
                challenge_id=request.challenge_id,
                account_type=AccountType(request.account_type),
                initial_balance=request.initial_balance,
                current_balance=request.initial_balance,
                current_equity=request.initial_balance,
                status=ChallengeStatus.ACTIVE,
                challenge_config=challenge_config,
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
            
            # Store account
            self.accounts[account.login] = account
            
            logger.info(f"Created trading account {account.login} for challenge {request.challenge_id}")
            return account
            
        except Exception as e:
            logger.error(f"Error creating trading account: {str(e)}")
            raise
    
    async def update_account_status(self, login: int, status: ChallengeStatus, reason: str = ""):
        """Update account status"""
        if login not in self.accounts:
            raise ValueError(f"Account {login} not found")
        
        account = self.accounts[login]
        old_status = account.status
        account.status = status
        account.last_updated = datetime.utcnow()
        
        logger.info(f"Account {login} status changed: {old_status} -> {status}. Reason: {reason}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop for all accounts"""
        while self.is_running:
            try:
                await self._monitor_accounts()
                await asyncio.sleep(60)  # Monitor every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _monitor_accounts(self):
        """Monitor all active accounts"""
        for login, account in self.accounts.items():
            if account.status == ChallengeStatus.ACTIVE:
                try:
                    await self._check_account_rules(account)
                except Exception as e:
                    logger.error(f"Error monitoring account {login}: {str(e)}")
    
    async def _check_account_rules(self, account: TradingAccount):
        """Check if account violates any challenge rules"""
        # Get current account info from MT server
        account_info = await self.finxsol_client.get_account_info(account.login)
        if not account_info:
            logger.warning(f"Could not get account info for {account.login}")
            return
        
        # Update account data
        account.current_balance = account_info['balance']
        account.current_equity = account_info['equity']
        account.last_updated = datetime.utcnow()
        
        # Calculate current drawdown
        current_drawdown = (account.initial_balance - account.current_equity) / account.initial_balance * 100
        account.total_drawdown = max(account.total_drawdown, current_drawdown)
        
        # Check maximum drawdown rule
        if current_drawdown > account.challenge_config.max_total_loss_percent:
            await self.update_account_status(
                account.login, 
                ChallengeStatus.FAILED,
                f"Maximum drawdown exceeded: {current_drawdown:.2f}%"
            )
            return
        
        # Calculate daily loss
        today = datetime.utcnow().strftime('%Y-%m-%d')
        if today not in account.daily_losses:
            account.daily_losses[today] = 0.0
        
        daily_loss_percent = account.daily_losses[today] / account.initial_balance * 100
        if daily_loss_percent > account.challenge_config.max_daily_loss_percent:
            await self.update_account_status(
                account.login,
                ChallengeStatus.FAILED,
                f"Daily loss limit exceeded: {daily_loss_percent:.2f}%"
            )
            return
        
        # Check profit target
        profit_percent = (account.current_equity - account.initial_balance) / account.initial_balance * 100
        if profit_percent >= account.challenge_config.profit_target_percent:
            await self.update_account_status(
                account.login,
                ChallengeStatus.PASSED,
                f"Profit target achieved: {profit_percent:.2f}%"
            )
            return
        
        # Check time limits (simplified)
        days_active = (datetime.utcnow() - account.created_at).days
        if days_active > account.challenge_config.maximum_trading_days:
            await self.update_account_status(
                account.login,
                ChallengeStatus.FAILED,
                "Maximum trading days exceeded"
            )

# Global manager instance
manager: Optional[PropFirmManager] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    global manager
    
    # Startup
    config = {
        'server_host': os.getenv("METATRADER_SERVER"),
        'port': os.getenv("METATRADER_PORT"),
        'manager_login': os.getenv("METATRADER_LOGIN"),  # Replace with actual manager login
        'manager_password': os.getenv("METATRADER_PASSWORD"),  # Replace with actual password
    }
    
    manager = PropFirmManager(config)
    await manager.start()
    
    yield
    
    # Shutdown
    if manager:
        await manager.stop()

# FastAPI app
app = FastAPI(
    title="PropFirm Account Manager",
    description="MetaTrader account management for prop firm challenges",
    version="1.0.0",
    lifespan=lifespan
)

@app.post("/accounts/create", response_model=AccountResponse)
async def create_account(request: CreateAccountRequest):
    """Create a new trading account"""
    try:
        account = await manager.create_trading_account(request)
        return AccountResponse(
            account_id=account.account_id,
            login=account.login,
            challenge_id=account.challenge_id,
            status=account.status.value,
            current_balance=account.current_balance,
            current_equity=account.current_equity,
            created_at=account.created_at
        )
    except Exception as e:
        logger.error(f"Error creating account: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/accounts/{login}", response_model=AccountResponse)
async def get_account(login: int):
    """Get account information"""
    if login not in manager.accounts:
        raise HTTPException(status_code=404, detail="Account not found")
    
    account = manager.accounts[login]
    return AccountResponse(
        account_id=account.account_id,
        login=account.login,
        challenge_id=account.challenge_id,
        status=account.status.value,
        current_balance=account.current_balance,
        current_equity=account.current_equity,
        created_at=account.created_at
    )

@app.get("/accounts")
async def list_accounts(status: Optional[str] = None):
    """List all accounts with optional status filter"""
    accounts = manager.accounts.values()
    
    if status:
        accounts = [acc for acc in accounts if acc.status.value == status]
    
    return [
        {
            "login": acc.login,
            "challenge_id": acc.challenge_id,
            "status": acc.status.value,
            "current_balance": acc.current_balance,
            "current_equity": acc.current_equity,
            "created_at": acc.created_at
        }
        for acc in accounts
    ]

@app.patch("/challenges/{challenge_id}")
async def update_challenge(challenge_id: str, request: ChallengeUpdateRequest):
    """Update challenge status or add notes"""
    # Find account by challenge_id
    account = None
    for acc in manager.accounts.values():
        if acc.challenge_id == challenge_id:
            account = acc
            break
    
    if not account:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    if request.status:
        try:
            new_status = ChallengeStatus(request.status)
            await manager.update_account_status(account.login, new_status, request.notes or "Manual update")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    
    return {"message": "Challenge updated successfully"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "authenticated": manager.finxsol_client.authenticated if manager else False,
        "active_accounts": len([acc for acc in manager.accounts.values() if acc.status == ChallengeStatus.ACTIVE]) if manager else 0,
        "timestamp": datetime.utcnow()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)