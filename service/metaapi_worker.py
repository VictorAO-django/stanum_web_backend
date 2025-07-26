import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
from contextlib import asynccontextmanager
from decimal import Decimal

# Django setup - MUST be before Django imports
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "stanum.settings")  # Replace with your project name
import django
django.setup()

# Now import Django models and utilities
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from django.conf import settings

# Import your Django models (adjust imports to match your models)
# from your_app.models import TradingAccount, Trade, AccountActivity, UserProfile

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import uvicorn
from metaapi_cloud_sdk import MetaApi

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models for API requests/responses
class AccountCreateRequest(BaseModel):
    user_id: int
    account_type: str  # 'challenge' or 'funded'
    balance: float = 100000
    name: Optional[str] = None
    server: str = "MetaQuotes-Demo"
    leverage: int = 100

class TradeRequest(BaseModel):
    account_id: str
    symbol: str
    action: str  # 'buy' or 'sell'
    volume: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: Optional[str] = None

class AccountResponse(BaseModel):
    account_id: str
    login: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    state: str

class RiskLimits(BaseModel):
    daily_loss_limit: float = 0.05  # 5%
    max_drawdown: float = 0.10      # 10%
    profit_target: float = 0.08     # 8%
    max_daily_trades: int = 50

# Django Model Placeholders - Replace with your actual models
class TradingAccount:
    """Replace this with your actual Django model import"""
    pass

class Trade:
    """Replace this with your actual Django model import"""
    pass

class AccountActivity:
    """Replace this with your actual Django model import"""  
    pass

# In-memory storage for active connections and real-time data
active_connections: Dict[str, Any] = {}
account_daily_stats: Dict[str, Dict] = {}

# MetaAPI connection manager with Django integration
class MetaAPIManager:
    def __init__(self, token: str):
        self.api = MetaApi(token)
        self.connections = {}
        
    async def create_account(self, request: AccountCreateRequest) -> dict:
        """Create a new MT5 account and save to Django models"""
        try:
            # Validate user exists in Django
            try:
                django_user = User.objects.get(id=request.user_id)
            except User.DoesNotExist:
                raise HTTPException(status_code=404, detail="User not found")
            
            # Generate unique login
            login = f"{request.account_type[:4]}{request.user_id}{timezone.now().strftime('%H%M%S')}"
            password = f"Pass{request.user_id}{timezone.now().strftime('%m%d')}!"
            
            # Create account on MetaAPI
            account = await self.api.metatrader_account_api.create_account({
                'name': request.name or f"{request.account_type}_{django_user.username}",
                'type': 'demo',
                'login': login,
                'password': password,
                'server': request.server,
                'provisioningProfileId': os.getenv('PROVISIONING_PROFILE_ID'),
                'application': 'MetaApi',
                'magic': 123456,
                'quoteStreamingIntervalInSeconds': 2.5,
            })
            
            # Wait for deployment
            logger.info(f"Deploying account {account.id}...")
            await account.deploy()
            await account.wait_deployed(timeout_in_seconds=300)
            
            # Create connection
            connection = account.get_rpc_connection()
            await connection.connect()
            await connection.wait_synchronized(timeout_in_seconds=300)
            
            # Store connection
            self.connections[account.id] = {
                'account': account,
                'connection': connection,
                'user_id': request.user_id,
                'account_type': request.account_type
            }
            
            # Save to Django database
            with transaction.atomic():
                # Replace this with your actual Django model creation
                """
                django_account = TradingAccount.objects.create(
                    user=django_user,
                    metaapi_account_id=account.id,
                    login=login,
                    password=password,  # Consider encrypting this
                    account_type=request.account_type,
                    balance=Decimal(str(request.balance)),
                    equity=Decimal(str(request.balance)),
                    server=request.server,
                    leverage=request.leverage,
                    status='active',
                    created_at=timezone.now(),
                    risk_daily_loss_limit=Decimal('0.05'),
                    risk_max_drawdown=Decimal('0.10'),
                    risk_profit_target=Decimal('0.08'),
                    max_daily_trades=50
                )
                """
                
                # Log account creation activity
                """
                AccountActivity.objects.create(
                    account=django_account,
                    activity_type='account_created',
                    description=f'Account created with balance {request.balance}',
                    timestamp=timezone.now()
                )
                """
            
            # Initialize daily stats tracking
            today = timezone.now().date().isoformat()
            account_daily_stats[account.id] = {
                'date': today,
                'starting_balance': request.balance,
                'starting_equity': request.balance,
                'highest_equity': request.balance,
                'trades_count': 0,
                'daily_pnl': 0.0
            }
            
            # Setup listeners
            await self._setup_listeners(account.id)
            
            logger.info(f"Successfully created account {account.id} for user {request.user_id}")
            
            return {
                'success': True,
                'account_id': account.id,
                'login': login,
                'balance': request.balance,
                'message': 'Account created successfully'
            }
            
        except Exception as e:
            logger.error(f"Error creating account: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")
    
    async def _setup_listeners(self, account_id: str):
        """Setup MetaAPI listeners for real-time updates"""
        try:
            connection = self.connections[account_id]['connection']
            
            # Position listener
            class PositionListener:
                def __init__(self, manager_instance):
                    self.manager = manager_instance
                
                async def on_position_updated(self, instance_index: str, position):
                    await self.manager._handle_position_update(account_id, position)
                
                async def on_position_removed(self, instance_index: str, position_id: str):
                    await self.manager._handle_position_removed(account_id, position_id)
            
            # Account information listener
            class AccountListener:
                def __init__(self, manager_instance):
                    self.manager = manager_instance
                
                async def on_account_information_updated(self, instance_index: str, account_information):
                    await self.manager._handle_account_update(account_id, account_information)
            
            # Trade listener
            class TradeListener:
                def __init__(self, manager_instance):
                    self.manager = manager_instance
                
                async def on_deal_added(self, instance_index: str, deal):
                    await self.manager._handle_deal_added(account_id, deal)
            
            # Add listeners
            connection.add_synchronization_listener(PositionListener(self))
            connection.add_synchronization_listener(AccountListener(self))
            connection.add_synchronization_listener(TradeListener(self))
            
            logger.info(f"Listeners setup completed for account {account_id}")
            
        except Exception as e:
            logger.error(f"Error setting up listeners for {account_id}: {str(e)}")
    
    async def _handle_position_update(self, account_id: str, position):
        """Handle position updates and save to Django"""
        try:
            logger.info(f"Position update for account {account_id}: {position}")
            
            # Update Django models
            with transaction.atomic():
                """
                # Get the Django account
                django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                
                # Update or create trade record
                trade, created = Trade.objects.update_or_create(
                    account=django_account,
                    position_id=position['id'],
                    defaults={
                        'symbol': position['symbol'],
                        'type': position['type'],
                        'volume': Decimal(str(position['volume'])),
                        'open_price': Decimal(str(position['openPrice'])),
                        'current_price': Decimal(str(position.get('currentPrice', position['openPrice']))),
                        'profit': Decimal(str(position.get('profit', 0))),
                        'swap': Decimal(str(position.get('swap', 0))),
                        'commission': Decimal(str(position.get('commission', 0))),
                        'open_time': datetime.fromisoformat(position['time'].replace('Z', '+00:00')),
                        'updated_at': timezone.now()
                    }
                )
                
                if created:
                    # Increment daily trades count
                    if account_id in account_daily_stats:
                        account_daily_stats[account_id]['trades_count'] += 1
                """
            
            # Check risk management after position update
            await self._check_risk_limits(account_id)
            
        except Exception as e:
            logger.error(f"Error handling position update: {str(e)}")
    
    async def _handle_position_removed(self, account_id: str, position_id: str):
        """Handle position closure"""
        try:
            logger.info(f"Position {position_id} closed for account {account_id}")
            
            with transaction.atomic():
                """
                # Update trade record as closed
                try:
                    django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                    trade = Trade.objects.get(
                        account=django_account,
                        position_id=position_id
                    )
                    trade.status = 'closed'
                    trade.close_time = timezone.now()
                    trade.save()
                    
                    # Log activity
                    AccountActivity.objects.create(
                        account=django_account,
                        activity_type='position_closed',
                        description=f'Position {position_id} closed with profit: {trade.profit}',
                        timestamp=timezone.now(),
                        related_trade=trade
                    )
                except Trade.DoesNotExist:
                    logger.warning(f"Trade with position_id {position_id} not found")
                """
            
        except Exception as e:
            logger.error(f"Error handling position removal: {str(e)}")
    
    async def _handle_account_update(self, account_id: str, account_info):
        """Handle account information updates"""
        try:
            logger.info(f"Account update for {account_id}: Balance={account_info.get('balance')}, Equity={account_info.get('equity')}")
            
            # Update daily stats
            if account_id in account_daily_stats:
                current_equity = float(account_info.get('equity', 0))
                stats = account_daily_stats[account_id]
                
                # Update highest equity for drawdown calculation
                if current_equity > stats['highest_equity']:
                    stats['highest_equity'] = current_equity
                
                # Calculate daily P&L
                stats['daily_pnl'] = current_equity - stats['starting_equity']
            
            # Update Django model
            with transaction.atomic():
                """
                django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                django_account.balance = Decimal(str(account_info.get('balance', django_account.balance)))
                django_account.equity = Decimal(str(account_info.get('equity', django_account.equity)))
                django_account.margin = Decimal(str(account_info.get('margin', 0)))
                django_account.free_margin = Decimal(str(account_info.get('freeMargin', 0)))
                django_account.margin_level = Decimal(str(account_info.get('marginLevel', 0)))
                django_account.updated_at = timezone.now()
                django_account.save()
                """
            
            # Check risk limits
            await self._check_risk_limits(account_id)
            
        except Exception as e:
            logger.error(f"Error handling account update: {str(e)}")
    
    async def _handle_deal_added(self, account_id: str, deal):
        """Handle new deals/trades"""
        try:
            logger.info(f"New deal for account {account_id}: {deal}")
            
            with transaction.atomic():
                """
                django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                
                # Log deal activity
                AccountActivity.objects.create(
                    account=django_account,
                    activity_type='deal_executed',
                    description=f"Deal executed: {deal.get('type')} {deal.get('volume')} {deal.get('symbol')} at {deal.get('price')}",
                    timestamp=timezone.now(),
                    metadata={'deal': deal}
                )
                """
            
        except Exception as e:
            logger.error(f"Error handling deal: {str(e)}")
    
    async def _check_risk_limits(self, account_id: str):
        """Check if account violates risk limits"""
        try:
            if account_id not in account_daily_stats:
                return
            
            stats = account_daily_stats[account_id]
            current_equity = stats['highest_equity'] + stats['daily_pnl']
            
            # Get account risk settings from Django
            """
            django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
            daily_loss_limit = float(django_account.risk_daily_loss_limit)
            max_drawdown = float(django_account.risk_max_drawdown)
            profit_target = float(django_account.risk_profit_target)
            max_trades = django_account.max_daily_trades
            """
            
            # Placeholder values - replace with actual Django model fields
            daily_loss_limit = 0.05
            max_drawdown = 0.10
            profit_target = 0.08
            max_trades = 50
            
            violation_reason = None
            
            # Check daily loss limit
            daily_loss_pct = abs(stats['daily_pnl']) / stats['starting_equity']
            if stats['daily_pnl'] < 0 and daily_loss_pct >= daily_loss_limit:
                violation_reason = f"Daily loss limit exceeded: {daily_loss_pct:.2%}"
            
            # Check max drawdown
            drawdown_pct = (stats['highest_equity'] - current_equity) / stats['highest_equity']
            if drawdown_pct >= max_drawdown:
                violation_reason = f"Maximum drawdown exceeded: {drawdown_pct:.2%}"
            
            # Check daily trades limit
            if stats['trades_count'] >= max_trades:
                violation_reason = f"Daily trades limit exceeded: {stats['trades_count']}/{max_trades}"
            
            # Check profit target (for challenge accounts)
            account_type = self.connections[account_id]['account_type']
            if account_type == 'challenge':
                profit_pct = stats['daily_pnl'] / stats['starting_equity']
                if profit_pct >= profit_target:
                    await self._promote_to_funded(account_id)
                    return
            
            # Disable account if violation found
            if violation_reason:
                await self._disable_account(account_id, violation_reason)
                
        except Exception as e:
            logger.error(f"Error checking risk limits: {str(e)}")
    
    async def _disable_account(self, account_id: str, reason: str):
        """Disable trading on account due to rule violation"""
        try:
            logger.warning(f"Disabling account {account_id}: {reason}")
            
            # Close all positions
            if account_id in self.connections:
                connection = self.connections[account_id]['connection']
                positions = await connection.get_positions()
                
                for position in positions:
                    try:
                        await connection.close_position(position['id'])
                        logger.info(f"Closed position {position['id']} due to account disable")
                    except Exception as e:
                        logger.error(f"Error closing position {position['id']}: {e}")
            
            # Update Django model
            with transaction.atomic():
                """
                django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                django_account.status = 'disabled'
                django_account.disable_reason = reason
                django_account.disabled_at = timezone.now()
                django_account.save()
                
                # Log activity
                AccountActivity.objects.create(
                    account=django_account,
                    activity_type='account_disabled',
                    description=f'Account disabled: {reason}',
                    timestamp=timezone.now()
                )
                """
            
            logger.info(f"Account {account_id} successfully disabled")
            
        except Exception as e:
            logger.error(f"Error disabling account: {str(e)}")
    
    async def _promote_to_funded(self, account_id: str):
        """Promote challenge account to funded status"""
        try:
            logger.info(f"Promoting challenge account {account_id} to funded status")
            
            user_id = self.connections[account_id]['user_id']
            
            with transaction.atomic():
                """
                # Update challenge account status
                challenge_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                challenge_account.status = 'challenge_passed'
                challenge_account.completed_at = timezone.now()
                challenge_account.save()
                
                # Log activity
                AccountActivity.objects.create(
                    account=challenge_account,
                    activity_type='challenge_passed',
                    description='Challenge completed successfully',
                    timestamp=timezone.now()
                )
                """
            
            # Auto-create funded account
            funded_request = AccountCreateRequest(
                user_id=user_id,
                account_type='funded',
                balance=200000,  # Larger funded account
                name=f"funded_{user_id}_{timezone.now().strftime('%Y%m%d')}"
            )
            
            funded_result = await self.create_account(funded_request)
            logger.info(f"Auto-created funded account for user {user_id}: {funded_result}")
            
        except Exception as e:
            logger.error(f"Error promoting account: {str(e)}")
    
    async def execute_trade(self, request: TradeRequest) -> dict:
        """Execute a trade"""
        try:
            if request.account_id not in self.connections:
                raise HTTPException(status_code=404, detail="Account connection not found")
            
            # Check if account is active
            """
            django_account = TradingAccount.objects.get(metaapi_account_id=request.account_id)
            if django_account.status != 'active':
                raise HTTPException(status_code=403, detail=f"Account is {django_account.status}")
            """
            
            connection = self.connections[request.account_id]['connection']
            
            # Prepare trade request
            trade_request = {
                'symbol': request.symbol,
                'type': 'ORDER_TYPE_BUY' if request.action.lower() == 'buy' else 'ORDER_TYPE_SELL',
                'volume': request.volume,
            }
            
            if request.stop_loss:
                trade_request['stopLoss'] = request.stop_loss
            if request.take_profit:
                trade_request['takeProfit'] = request.take_profit
            if request.comment:
                trade_request['comment'] = request.comment
            
            # Execute trade
            result = await connection.create_market_order(trade_request)
            
            logger.info(f"Trade executed successfully: {result}")
            
            return {
                'success': True,
                'order_id': result.get('orderId'),
                'message': 'Trade executed successfully'
            }
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Trade execution failed: {str(e)}")
    
    async def get_account_status(self, account_id: str) -> dict:
        """Get comprehensive account status"""
        try:
            # Get real-time data from MetaAPI
            if account_id in self.connections:
                connection = self.connections[account_id]['connection']
                account_info = await connection.get_account_information()
                positions = await connection.get_positions()
            else:
                raise HTTPException(status_code=404, detail="Account connection not found")
            
            # Get Django model data
            """
            django_account = TradingAccount.objects.get(metaapi_account_id=account_id)
            recent_trades = Trade.objects.filter(account=django_account).order_by('-open_time')[:10]
            """
            
            # Get daily stats
            daily_stats = account_daily_stats.get(account_id, {})
            
            return {
                'success': True,
                'account_id': account_id,
                'real_time': {
                    'balance': account_info.balance,
                    'equity': account_info.equity,
                    'margin': account_info.margin,
                    'free_margin': account_info.freeMargin,
                    'margin_level': account_info.marginLevel,
                    'positions_count': len(positions)
                },
                'daily_stats': daily_stats,
                # 'recent_trades': [self._serialize_trade(trade) for trade in recent_trades],
                'positions': positions
            }
            
        except Exception as e:
            logger.error(f"Error getting account status: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

# Initialize MetaAPI manager
metaapi_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global metaapi_manager
    token = os.getenv('METAAPI_TOKEN')
    if not token:
        raise ValueError("METAAPI_TOKEN environment variable is required")
    
    metaapi_manager = MetaAPIManager(token)
    logger.info("MetaAPI Manager initialized with Django integration")
    
    # Reset daily stats at startup
    asyncio.create_task(reset_daily_stats_scheduler())
    
    yield
    # Shutdown
    logger.info("Shutting down MetaAPI connections")
    for account_id, conn_info in metaapi_manager.connections.items():
        try:
            await conn_info['connection'].disconnect()
        except:
            pass

async def reset_daily_stats_scheduler():
    """Reset daily stats at midnight"""
    while True:
        now = timezone.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        sleep_seconds = (tomorrow - now).total_seconds()
        
        await asyncio.sleep(sleep_seconds)
        
        # Reset daily stats for all accounts
        for account_id in account_daily_stats:
            if account_id in metaapi_manager.connections:
                try:
                    connection = metaapi_manager.connections[account_id]['connection']
                    account_info = await connection.get_account_information()
                    
                    account_daily_stats[account_id] = {
                        'date': timezone.now().date().isoformat(),
                        'starting_balance': float(account_info.balance),
                        'starting_equity': float(account_info.equity),
                        'highest_equity': float(account_info.equity),
                        'trades_count': 0,
                        'daily_pnl': 0.0
                    }
                except Exception as e:
                    logger.error(f"Error resetting daily stats for {account_id}: {e}")

# Create FastAPI app
app = FastAPI(
    title="MetaAPI Trading Service with Django Integration",
    description="Standalone service for handling MetaAPI connections with direct Django model integration",
    version="1.0.0",
    lifespan=lifespan
)

# API Endpoints
@app.post("/accounts/create")
async def create_account(request: AccountCreateRequest):
    """Create a new trading account"""
    result = await metaapi_manager.create_account(request)
    return result

@app.get("/accounts/{account_id}/status")
async def get_account_status(account_id: str):
    """Get comprehensive account status"""
    return await metaapi_manager.get_account_status(account_id)

@app.post("/trades/execute")
async def execute_trade(request: TradeRequest):
    """Execute a trade"""
    return await metaapi_manager.execute_trade(request)

@app.get("/accounts/{account_id}/positions")
async def get_positions(account_id: str):
    """Get current positions"""
    try:
        if account_id not in metaapi_manager.connections:
            raise HTTPException(status_code=404, detail="Account not found")
        
        connection = metaapi_manager.connections[account_id]['connection']
        positions = await connection.get_positions()
        
        return {
            'success': True,
            'positions': positions
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/accounts/{account_id}/close-position/{position_id}")
async def close_position(account_id: str, position_id: str):
    """Close a specific position"""
    try:
        if account_id not in metaapi_manager.connections:
            raise HTTPException(status_code=404, detail="Account not found")
        
        connection = metaapi_manager.connections[account_id]['connection']
        await connection.close_position(position_id)
        
        return {
            'success': True,
            'message': 'Position closed successfully'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/accounts/{account_id}/close-all-positions")
async def close_all_positions(account_id: str):
    """Close all positions for an account"""
    try:
        if account_id not in metaapi_manager.connections:
            raise HTTPException(status_code=404, detail="Account not found")
        
        connection = metaapi_manager.connections[account_id]['connection']
        positions = await connection.get_positions()
        
        closed_count = 0
        for position in positions:
            try:
                await connection.close_position(position['id'])
                closed_count += 1
            except Exception as e:
                logger.error(f"Error closing position {position['id']}: {e}")
        
        return {
            'success': True,
            'message': f'Closed {closed_count} positions',
            'closed_count': closed_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/accounts/{account_id}/equity")
async def get_account_equity(account_id: str):
    """Get real-time account equity"""
    try:
        if account_id not in metaapi_manager.connections:
            raise HTTPException(status_code=404, detail="Account not found")
        
        connection = metaapi_manager.connections[account_id]['connection']
        account_info = await connection.get_account_information()
        
        return {
            'success': True,
            'equity': account_info.equity,
            'balance': account_info.balance,
            'margin': account_info.margin,
            'free_margin': account_info.freeMargin,
            'margin_level': account_info.marginLevel,
            'daily_stats': account_daily_stats.get(account_id, {})
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/accounts")
async def list_accounts():
    """List all active accounts"""
    try:
        accounts_list = []
        for account_id, conn_info in metaapi_manager.connections.items():
            try:
                connection = conn_info['connection']
                account_info = await connection.get_account_information()
                
                accounts_list.append({
                    'account_id': account_id,
                    'user_id': conn_info['user_id'],
                    'account_type': conn_info['account_type'],
                    'balance': account_info.balance,
                    'equity': account_info.equity,
                    'daily_stats': account_daily_stats.get(account_id, {})
                })
            except Exception as e:
                logger.error(f"Error getting info for account {account_id}: {e}")
        
        return {
            'success': True,
            'accounts': accounts_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'active_accounts': len(metaapi_manager.connections) if metaapi_manager else 0,
        'django_connection': 'active' if django else 'inactive'
    }

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # Disable reload due to Django setup
        log_level="info"
    )