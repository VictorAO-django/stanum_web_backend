#!/usr/bin/env python3
"""
MT4/MT5 PropFirm Manager Script
Standalone asyncio application for real-time account monitoring and risk management.
FastAPI is just one component for external communication.
"""

import os
import sys
import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Set
import json
from dataclasses import dataclass
import threading
from contextlib import asynccontextmanager

# FastAPI imports (optional component)
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import uvicorn

# MetaAPI imports
from metaapi_cloud_sdk import MetaApi, SynchronizationListener, HistoryStorage

# Django setup
import django
from django.conf import settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

from django.utils import timezone as django_timezone
from django.db import transaction
from django.db.models import Sum
from trading.models import (  # Replace 'your_app' with actual app name
    TradingAccount, Trade, AccountActivity, DailyAccountStats, UserProfile
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mt_manager.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration
METAAPI_TOKEN = os.getenv('METAAPI_TOKEN')
RISK_CHECK_INTERVAL = 5  # seconds
STATS_UPDATE_INTERVAL = 300  # 5 minutes
HEARTBEAT_INTERVAL = 30  # seconds
ACCOUNT_DISCOVERY_INTERVAL = 60  # Check for new accounts every minute
MAX_RECONNECTION_ATTEMPTS = 5

@dataclass
class RiskViolation:
    account_id: str
    violation_type: str
    current_value: Decimal
    limit_value: Decimal
    severity: str  # 'warning', 'critical'

class PropFirmSynchronizationListener(SynchronizationListener):
    """Custom synchronization listener for prop firm risk management"""
    
    def __init__(self, manager):
        self.manager = manager
        super().__init__()
        
    async def on_account_information_updated(self, instance_index: str, account_information: dict):
        """Handle real-time account information updates"""
        try:
            await self.manager.handle_account_update(instance_index, account_information)
        except Exception as e:
            logger.error(f"Error handling account update for {instance_index}: {e}")
    
    async def on_position_updated(self, instance_index: str, position: dict):
        """Handle real-time position updates"""
        try:
            await self.manager.handle_position_update(instance_index, position)
        except Exception as e:
            logger.error(f"Error handling position update for {instance_index}: {e}")
    
    async def on_position_removed(self, instance_index: str, position_id: str):
        """Handle position closure"""
        try:
            await self.manager.handle_position_closed(instance_index, position_id)
        except Exception as e:
            logger.error(f"Error handling position closure for {instance_index}: {e}")
    
    async def on_deal_added(self, instance_index: str, deal: dict):
        """Handle new deals (trades)"""
        try:
            await self.manager.handle_deal_added(instance_index, deal)
        except Exception as e:
            logger.error(f"Error handling deal for {instance_index}: {e}")
    
    async def on_synchronization_started(self, instance_index: str):
        """Handle synchronization start"""
        account_id = instance_index.split(':')[0]
        logger.info(f"Synchronization started for account {account_id}")
    
    async def on_connected(self, instance_index: str, replicas: int):
        """Handle connection establishment"""
        account_id = instance_index.split(':')[0]
        logger.info(f"Connected to account {account_id} with {replicas} replicas")
    
    async def on_disconnected(self, instance_index: str):
        """Handle disconnection"""
        account_id = instance_index.split(':')[0]
        logger.warning(f"Disconnected from account {account_id}")
        await self.manager.handle_disconnection(account_id)


class ConnectionManager:
    """Manages MetaAPI connections with automatic reconnection"""
    
    def __init__(self):
        self.connections: Dict[str, Any] = {}
        self.connection_attempts: Dict[str, int] = {}
        self.failed_connections: Set[str] = set()
    
    async def add_connection(self, account_id: str, connection):
        """Add a connection to the manager"""
        self.connections[account_id] = connection
        self.connection_attempts[account_id] = 0
        self.failed_connections.discard(account_id)
        logger.info(f"Added connection for account {account_id}")
    
    async def remove_connection(self, account_id: str):
        """Remove a connection from the manager"""
        if account_id in self.connections:
            try:
                await self.connections[account_id].close()
            except Exception as e:
                logger.error(f"Error closing connection for {account_id}: {e}")
            del self.connections[account_id]
        
        self.connection_attempts.pop(account_id, None)
        logger.info(f"Removed connection for account {account_id}")
    
    async def reconnect_account(self, account_id: str, manager):
        """Attempt to reconnect a failed account"""
        if account_id in self.failed_connections:
            attempts = self.connection_attempts.get(account_id, 0)
            if attempts < MAX_RECONNECTION_ATTEMPTS:
                try:
                    account = TradingAccount.objects.get(metaapi_account_id=account_id)
                    await manager.setup_account_connection(account)
                    return True
                except Exception as e:
                    self.connection_attempts[account_id] = attempts + 1
                    logger.error(f"Reconnection attempt {attempts + 1} failed for {account_id}: {e}")
            else:
                logger.error(f"Max reconnection attempts reached for account {account_id}")
        return False
    
    def mark_failed(self, account_id: str):
        """Mark an account connection as failed"""
        self.failed_connections.add(account_id)
        self.remove_connection(account_id)
    
    def get_connection(self, account_id: str):
        """Get connection for account"""
        return self.connections.get(account_id)
    
    def is_connected(self, account_id: str) -> bool:
        """Check if account is connected"""
        return account_id in self.connections
    
    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.connections)


class MT45Manager:
    """Main manager class for MT4/MT5 prop firm operations"""
    
    def __init__(self):
        self.api = MetaApi(METAAPI_TOKEN)
        self.connection_manager = ConnectionManager()
        self.accounts: Dict[str, TradingAccount] = {}
        self.listener = PropFirmSynchronizationListener(self)
        self.running = False
        self.tasks: List[asyncio.Task] = []
        self.last_account_check = datetime.min
        self.known_account_ids: Set[str] = set()  # Track known account IDs
        
    async def initialize(self):
        """Initialize MetaAPI connections for all active accounts"""
        logger.info("Initializing MT4/MT5 Manager...")
        
        # Load all active trading accounts
        active_accounts = TradingAccount.objects.filter(status='active')
        logger.info(f"Found {active_accounts.count()} active accounts")
        
        # Track known account IDs
        self.known_account_ids = set(account.metaapi_account_id for account in active_accounts)
        
        connection_tasks = []
        for account in active_accounts:
            task = asyncio.create_task(self.setup_account_connection(account))
            connection_tasks.append(task)
        
        # Wait for all connections with timeout
        if connection_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*connection_tasks, return_exceptions=True),
                    timeout=60.0  # 60 seconds timeout for all connections
                )
            except asyncio.TimeoutError:
                logger.warning("Some connections timed out during initialization")
        
        self.last_account_check = datetime.now()
        logger.info(f"Initialized {self.connection_manager.get_connection_count()} account connections")
    
    async def setup_account_connection(self, account: TradingAccount):
        """Setup MetaAPI connection for a trading account"""
        try:
            logger.info(f"Setting up connection for account {account.metaapi_account_id}")
            
            # Get MetaAPI account
            meta_account = await self.api.metatrader_account_api.get_account(account.metaapi_account_id)
            
            # Wait for deployment (with timeout)
            await asyncio.wait_for(meta_account.deploy(), timeout=30.0)
            await asyncio.wait_for(meta_account.wait_deployed(), timeout=60.0)
            
            # Create connection
            connection = meta_account.get_streaming_connection()
            await asyncio.wait_for(connection.connect(), timeout=30.0)
            await asyncio.wait_for(connection.wait_synchronized(), timeout=120.0)
            
            # Add synchronization listener
            connection.add_synchronization_listener(self.listener)
            
            # Add to connection manager
            await self.connection_manager.add_connection(account.metaapi_account_id, connection)
            self.accounts[account.metaapi_account_id] = account
            
            logger.info(f"Successfully connected to account {account.metaapi_account_id}")
            
        except Exception as e:
            logger.error(f"Failed to connect to account {account.metaapi_account_id}: {e}")
            self.connection_manager.mark_failed(account.metaapi_account_id)
    
    async def handle_disconnection(self, account_id: str):
        """Handle account disconnection"""
        logger.warning(f"Handling disconnection for account {account_id}")
        self.connection_manager.mark_failed(account_id)
        
        # Schedule reconnection attempt
        asyncio.create_task(self.reconnect_account_delayed(account_id))
    
    async def discover_new_accounts(self):
        """Discover and connect to newly created accounts"""
        try:
            # Get all active accounts from database
            current_accounts = TradingAccount.objects.filter(status='active')
            current_account_ids = set(account.metaapi_account_id for account in current_accounts)
            
            # Find new accounts
            new_account_ids = current_account_ids - self.known_account_ids
            
            # Find removed/disabled accounts
            removed_account_ids = self.known_account_ids - current_account_ids
            
            # Handle new accounts
            if new_account_ids:
                logger.info(f"Discovered {len(new_account_ids)} new accounts: {new_account_ids}")
                
                for account_id in new_account_ids:
                    try:
                        account = TradingAccount.objects.get(metaapi_account_id=account_id, status='active')
                        await self.setup_account_connection(account)
                        
                        # Log account addition
                        await self.log_activity(account, 'account_created', 
                                              f"Account {account_id} discovered and connected")
                        
                    except TradingAccount.DoesNotExist:
                        logger.warning(f"Account {account_id} not found or not active")
                    except Exception as e:
                        logger.error(f"Failed to setup new account {account_id}: {e}")
            
            # Handle removed/disabled accounts
            if removed_account_ids:
                logger.info(f"Removing {len(removed_account_ids)} disabled accounts: {removed_account_ids}")
                
                for account_id in removed_account_ids:
                    await self.remove_account(account_id, "Account disabled or removed")
            
            # Update known account IDs
            self.known_account_ids = current_account_ids
            self.last_account_check = datetime.now()
            
            logger.debug(f"Account discovery complete. Managing {len(self.known_account_ids)} accounts")
            
        except Exception as e:
            logger.error(f"Error during account discovery: {e}")
    
    async def remove_account(self, account_id: str, reason: str):
        """Remove an account from management"""
        try:
            # Close connection
            await self.connection_manager.remove_connection(account_id)
            
            # Remove from tracking
            if account_id in self.accounts:
                account = self.accounts[account_id]
                del self.accounts[account_id]
                
                # Log removal
                await self.log_activity(account, 'account_disabled', 
                                      f"Account {account_id} removed from management: {reason}")
                
                logger.info(f"Removed account {account_id} from management: {reason}")
            
        except Exception as e:
            logger.error(f"Error removing account {account_id}: {e}")
    
    async def handle_account_status_change(self, account: TradingAccount, new_status: str):
        """Handle account status changes"""
        old_status = account.status
        
        if old_status == 'active' and new_status != 'active':
            # Account was disabled
            await self.remove_account(account.metaapi_account_id, f"Status changed to {new_status}")
            
        elif old_status != 'active' and new_status == 'active':
            # Account was re-enabled
            try:
                await self.setup_account_connection(account)
                await self.log_activity(account, 'account_created', 
                                      f"Account {account.metaapi_account_id} re-enabled and reconnected")
            except Exception as e:
                logger.error(f"Failed to reconnect re-enabled account {account.metaapi_account_id}: {e}")
    
    async def check_account_updates(self):
        """Check for account status updates and configuration changes"""
        try:
            # Check accounts that we're currently managing
            for account_id, managed_account in list(self.accounts.items()):
                try:
                    # Refresh account data from database
                    current_account = TradingAccount.objects.get(metaapi_account_id=account_id)
                    
                    # Check for status changes
                    if current_account.status != managed_account.status:
                        logger.info(f"Account {account_id} status changed: {managed_account.status} -> {current_account.status}")
                        await self.handle_account_status_change(current_account, current_account.status)
                    
                    # Update account in memory with latest data
                    if current_account.status == 'active':
                        self.accounts[account_id] = current_account
                    
                except TradingAccount.DoesNotExist:
                    # Account was deleted
                    logger.warning(f"Account {account_id} no longer exists, removing from management")
                    await self.remove_account(account_id, "Account deleted")
                
                except Exception as e:
                    logger.error(f"Error checking updates for account {account_id}: {e}")
            
        except Exception as e:
            logger.error(f"Error checking account updates: {e}")
    
    async def handle_account_update(self, instance_index: str, account_info: dict):
        """Process real-time account information updates"""
        account_id = instance_index.split(':')[0]
        
        if account_id not in self.accounts:
            return
        
        account = self.accounts[account_id]
        
        # Update account financial data
        try:
            with transaction.atomic():
                account.balance = Decimal(str(account_info.get('balance', 0)))
                account.equity = Decimal(str(account_info.get('equity', 0)))
                account.margin = Decimal(str(account_info.get('margin', 0)))
                account.free_margin = Decimal(str(account_info.get('freeMargin', 0)))
                account.margin_level = Decimal(str(account_info.get('marginLevel', 0)))
                account.save()
            
            # Perform risk checks
            await self.check_account_risk(account, account_info)
            
            logger.debug(f"Updated account {account_id}: Balance={account.balance}, Equity={account.equity}")
            
        except Exception as e:
            logger.error(f"Error updating account {account_id}: {e}")
    
    async def handle_position_update(self, instance_index: str, position: dict):
        """Process real-time position updates"""
        account_id = instance_index.split(':')[0]
        
        if account_id not in self.accounts:
            return
        
        account = self.accounts[account_id]
        position_id = position.get('id')
        
        try:
            # Update or create trade record
            with transaction.atomic():
                trade, created = Trade.objects.get_or_create(
                    account=account,
                    position_id=position_id,
                    defaults={
                        'symbol': position.get('symbol'),
                        'type': 'buy' if position.get('type') == 'POSITION_TYPE_BUY' else 'sell',
                        'volume': Decimal(str(position.get('volume', 0))),
                        'open_price': Decimal(str(position.get('openPrice', 0))),
                        'open_time': datetime.fromisoformat(position.get('time').replace('Z', '+00:00')),
                        'stop_loss': Decimal(str(position.get('stopLoss', 0))) if position.get('stopLoss') else None,
                        'take_profit': Decimal(str(position.get('takeProfit', 0))) if position.get('takeProfit') else None,
                    }
                )
                
                if not created:
                    # Update existing trade
                    trade.current_price = Decimal(str(position.get('currentPrice', 0)))
                    trade.profit = Decimal(str(position.get('profit', 0)))
                    trade.swap = Decimal(str(position.get('swap', 0)))
                    trade.commission = Decimal(str(position.get('commission', 0)))
                    trade.save()
            
            if created:
                # Log position opening
                await self.log_activity(account, 'position_opened', 
                                      f"Opened {trade.type.upper()} {trade.volume} {trade.symbol} at {trade.open_price}",
                                      related_trade=trade)
        
        except Exception as e:
            logger.error(f"Error handling position update for {account_id}: {e}")
    
    async def handle_position_closed(self, instance_index: str, position_id: str):
        """Handle position closure"""
        account_id = instance_index.split(':')[0]
        
        if account_id not in self.accounts:
            return
        
        account = self.accounts[account_id]
        
        try:
            with transaction.atomic():
                trade = Trade.objects.get(account=account, position_id=position_id, status='open')
                trade.status = 'closed'
                trade.close_time = django_timezone.now()
                trade.save()
                
                # Log position closure
                await self.log_activity(account, 'position_closed',
                                      f"Closed {trade.type.upper()} {trade.volume} {trade.symbol} - P&L: {trade.total_result}",
                                      related_trade=trade)
                
        except Trade.DoesNotExist:
            logger.warning(f"Trade {position_id} not found for account {account_id}")
        except Exception as e:
            logger.error(f"Error handling position closure for {account_id}: {e}")
    
    async def handle_deal_added(self, instance_index: str, deal: dict):
        """Handle new deals (executed trades)"""
        account_id = instance_index.split(':')[0]
        
        if account_id not in self.accounts:
            return
        
        account = self.accounts[account_id]
        
        try:
            # Log deal execution
            await self.log_activity(account, 'deal_executed',
                                  f"Deal executed: {deal.get('type')} {deal.get('volume')} {deal.get('symbol')} at {deal.get('price')}",
                                  metadata=deal)
        except Exception as e:
            logger.error(f"Error handling deal for {account_id}: {e}")
    
    async def check_account_risk(self, account: TradingAccount, account_info: dict):
        """Perform comprehensive risk checks on account"""
        try:
            violations = []
            equity = Decimal(str(account_info.get('equity', 0)))
            balance = Decimal(str(account_info.get('balance', 0)))
            
            # Daily loss limit check
            today_stats = await self.get_or_create_daily_stats(account)
            if today_stats.starting_equity > 0:
                daily_loss_pct = (today_stats.starting_equity - equity) / today_stats.starting_equity
                daily_loss_limit = account.risk_daily_loss_limit
                
                if daily_loss_pct > daily_loss_limit:
                    violations.append(RiskViolation(
                        account_id=account.metaapi_account_id,
                        violation_type='daily_loss_limit',
                        current_value=daily_loss_pct,
                        limit_value=daily_loss_limit,
                        severity='critical'
                    ))
            
            # Max drawdown check
            if today_stats.highest_equity > 0:
                drawdown_pct = (today_stats.highest_equity - equity) / today_stats.highest_equity
                max_drawdown = account.risk_max_drawdown
                
                if drawdown_pct > max_drawdown:
                    violations.append(RiskViolation(
                        account_id=account.metaapi_account_id,
                        violation_type='max_drawdown',
                        current_value=drawdown_pct,
                        limit_value=max_drawdown,
                        severity='critical'
                    ))
            
            # Process violations
            for violation in violations:
                await self.handle_risk_violation(account, violation)
        
        except Exception as e:
            logger.error(f"Error checking risk for account {account.metaapi_account_id}: {e}")
    
    async def handle_risk_violation(self, account: TradingAccount, violation: RiskViolation):
        """Handle risk violations"""
        logger.warning(f"Risk violation for account {account.metaapi_account_id}: {violation.violation_type}")
        
        try:
            if violation.severity == 'critical':
                # Close all positions and disable account
                await self.close_all_positions(account)
                await self.disable_account(account, f"Risk violation: {violation.violation_type}")
            
            # Log the violation
            await self.log_activity(account, 'risk_violation',
                                  f"Risk violation: {violation.violation_type} - {violation.current_value:.4f} > {violation.limit_value:.4f}",
                                  metadata=violation.__dict__)
        except Exception as e:
            logger.error(f"Error handling risk violation for {account.metaapi_account_id}: {e}")
    
    async def close_all_positions(self, account: TradingAccount):
        """Close all open positions for an account"""
        connection = self.connection_manager.get_connection(account.metaapi_account_id)
        if not connection:
            logger.warning(f"No connection available for account {account.metaapi_account_id}")
            return
        
        try:
            # Get all open positions
            positions = await connection.get_positions()
            
            close_tasks = []
            for position in positions:
                task = asyncio.create_task(self.close_position_safe(connection, position['id']))
                close_tasks.append(task)
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Failed to get positions for account {account.metaapi_account_id}: {e}")
    
    async def close_position_safe(self, connection, position_id: str):
        """Safely close a single position"""
        try:
            await connection.close_position(position_id)
            logger.info(f"Closed position {position_id}")
        except Exception as e:
            logger.error(f"Failed to close position {position_id}: {e}")
    
    async def disable_account(self, account: TradingAccount, reason: str):
        """Disable a trading account"""
        try:
            with transaction.atomic():
                account.status = 'disabled'
                account.disable_reason = reason
                account.disabled_at = django_timezone.now()
                account.save()
            
            await self.log_activity(account, 'account_disabled', reason)
            logger.info(f"Disabled account {account.metaapi_account_id}: {reason}")
        except Exception as e:
            logger.error(f"Error disabling account {account.metaapi_account_id}: {e}")
    
    async def log_activity(self, account: TradingAccount, activity_type: str, description: str, 
                          related_trade: Optional[Trade] = None, metadata: Optional[dict] = None):
        """Log account activity"""
        try:
            AccountActivity.objects.create(
                account=account,
                related_trade=related_trade,
                activity_type=activity_type,
                description=description,
                metadata=metadata or {}
            )
        except Exception as e:
            logger.error(f"Error logging activity for account {account.metaapi_account_id}: {e}")
    
    async def get_or_create_daily_stats(self, account: TradingAccount) -> DailyAccountStats:
        """Get or create daily statistics for an account"""
        today = django_timezone.now().date()
        
        try:
            stats, created = DailyAccountStats.objects.get_or_create(
                account=account,
                date=today,
                defaults={
                    'starting_balance': account.balance,
                    'starting_equity': account.equity,
                    'highest_equity': account.equity,
                    'lowest_equity': account.equity,
                }
            )
            
            if not created:
                # Update high/low equity
                if account.equity > stats.highest_equity:
                    stats.highest_equity = account.equity
                if account.equity < stats.lowest_equity:
                    stats.lowest_equity = account.equity
                
                stats.ending_equity = account.equity
                stats.daily_pnl = account.equity - stats.starting_equity
                stats.save()
            
            return stats
        except Exception as e:
            logger.error(f"Error getting daily stats for account {account.metaapi_account_id}: {e}")
            raise
    
    async def update_daily_stats(self):
        """Update daily statistics for all accounts"""
        today = django_timezone.now().date()
        
        for account_id, account in self.accounts.items():
            try:
                # Update trade counts
                daily_trades = Trade.objects.filter(
                    account=account,
                    open_time__date=today
                )
                
                winning_trades = daily_trades.filter(profit__gt=0).count()
                losing_trades = daily_trades.filter(profit__lt=0).count()
                
                # Update statistics
                stats = await self.get_or_create_daily_stats(account)
                stats.trades_count = daily_trades.count()
                stats.winning_trades = winning_trades
                stats.losing_trades = losing_trades
                stats.gross_profit = daily_trades.filter(profit__gt=0).aggregate(
                    total=Sum('profit'))['total'] or Decimal('0.00')
                stats.gross_loss = daily_trades.filter(profit__lt=0).aggregate(
                    total=Sum('profit'))['total'] or Decimal('0.00')
                stats.save()
                
            except Exception as e:
                logger.error(f"Error updating daily stats for account {account_id}: {e}")
    
    async def heartbeat_task(self):
        """Periodic heartbeat and health checks"""
        while self.running:
            try:
                logger.info(f"Heartbeat: {self.connection_manager.get_connection_count()} active connections")
                
                # Check for failed connections and attempt reconnection
                for account_id in list(self.connection_manager.failed_connections):
                    await self.connection_manager.reconnect_account(account_id, self)
                
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                logger.error(f"Error in heartbeat task: {e}")
                await asyncio.sleep(10)
    
    async def stats_update_task(self):
        """Background task for updating statistics"""
        while self.running:
            try:
                await self.update_daily_stats()
                await asyncio.sleep(STATS_UPDATE_INTERVAL)
            except Exception as e:
                logger.error(f"Error in stats update task: {e}")
                await asyncio.sleep(60)
    
    async def start(self):
        """Start the manager"""
        logger.info("Starting MT4/MT5 Manager...")
        self.running = True
        
        # Initialize connections
        await self.initialize()
        
        # Start background tasks
        self.tasks = [
            asyncio.create_task(self.heartbeat_task()),
            asyncio.create_task(self.stats_update_task()),
            asyncio.create_task(self.account_discovery_task()),  # New task for account discovery
        ]
        
        logger.info("MT4/MT5 Manager started successfully")
    
    async def stop(self):
        """Stop the manager"""
        logger.info("Stopping MT4/MT5 Manager...")
        self.running = False
        
        # Cancel background tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Close all connections
        for account_id in list(self.connection_manager.connections.keys()):
            await self.connection_manager.remove_connection(account_id)
        
        logger.info("MT4/MT5 Manager stopped")
    
    # API Methods for FastAPI integration
    def get_status(self):
        """Get manager status"""
        return {
            "running": self.running,
            "active_connections": self.connection_manager.get_connection_count(),
            "failed_connections": len(self.connection_manager.failed_connections),
            "managed_accounts": len(self.accounts),
            "known_accounts": len(self.known_account_ids),
            "last_account_check": self.last_account_check.isoformat() if self.last_account_check != datetime.min else None
        }
    
    def get_accounts_info(self):
        """Get information about all managed accounts"""
        accounts = []
        for account_id, account in self.accounts.items():
            accounts.append({
                "account_id": account_id,
                "user": account.user.username,
                "account_type": account.account_type,
                "status": account.status,
                "balance": float(account.balance),
                "equity": float(account.equity),
                "connected": self.connection_manager.is_connected(account_id),
                "failed": account_id in self.connection_manager.failed_connections
            })
        return accounts

# Global manager instance
manager = MT45Manager()

# FastAPI application (optional component)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown - manager will be stopped by main()

app = FastAPI(
    title="PropFirm MT4/MT5 Manager API",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        **manager.get_status(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/accounts")
async def get_accounts():
    """Get all managed accounts"""
    return manager.get_accounts_info()

@app.post("/accounts/{account_id}/disable")
async def disable_account_endpoint(account_id: str, reason: str = "Manual disable"):
    """Disable a trading account"""
    if account_id not in manager.accounts:
        raise HTTPException(status_code=404, detail="Account not found")
    
    account = manager.accounts[account_id]
    await manager.disable_account(account, reason)
    
    return {"message": f"Account {account_id} disabled successfully"}

@app.post("/accounts/{account_id}/close-positions")
async def close_positions_endpoint(account_id: str):
    """Close all positions for an account"""
    if account_id not in manager.accounts:
        raise HTTPException(status_code=404, detail="Account not found")
    
    account = manager.accounts[account_id]
    await manager.close_all_positions(account)
    
    return {"message": f"All positions closed for account {account_id}"}

@app.post("/accounts/discover")
async def discover_accounts_endpoint():
    """Manually trigger account discovery"""
    try:
        await manager.discover_new_accounts()
        return {
            "message": "Account discovery completed",
            "managed_accounts": len(manager.accounts),
            "known_accounts": len(manager.known_account_ids)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Account discovery failed: {str(e)}")

@app.post("/accounts/{account_id}/connect")
async def connect_account_endpoint(account_id: str):
    """Manually connect a specific account"""
    try:
        # Get account from database
        account = TradingAccount.objects.get(metaapi_account_id=account_id, status='active')
        
        # Check if already connected
        if manager.connection_manager.is_connected(account_id):
            return {"message": f"Account {account_id} is already connected"}
        
        # Setup connection
        await manager.setup_account_connection(account)
        
        return {"message": f"Account {account_id} connected successfully"}
        
    except TradingAccount.DoesNotExist:
        raise HTTPException(status_code=404, detail="Account not found or not active")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

@app.post("/accounts/{account_id}/disconnect")
async def disconnect_account_endpoint(account_id: str, reason: str = "Manual disconnect"):
    """Manually disconnect a specific account"""
    try:
        if account_id not in manager.accounts:
            raise HTTPException(status_code=404, detail="Account not found in manager")
        
        await manager.remove_account(account_id, reason)
        
        return {"message": f"Account {account_id} disconnected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Disconnection failed: {str(e)}")

@app.get("/accounts/{account_id}/connection-status")
async def get_connection_status(account_id: str):
    """Get detailed connection status for an account"""
    try:
        # Check if account exists in database
        try:
            account = TradingAccount.objects.get(metaapi_account_id=account_id)
            account_exists = True
        except TradingAccount.DoesNotExist:
            account_exists = False
            account = None
        
        return {
            "account_id": account_id,
            "exists_in_db": account_exists,
            "account_status": account.status if account else None,
            "managed": account_id in manager.accounts,
            "connected": manager.connection_manager.is_connected(account_id),
            "failed": account_id in manager.connection_manager.failed_connections,
            "connection_attempts": manager.connection_manager.connection_attempts.get(account_id, 0)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")

@app.get("/system/stats")
async def get_system_stats():
    """Get comprehensive system statistics"""
    try:
        # Database statistics
        total_accounts = TradingAccount.objects.count()
        active_accounts = TradingAccount.objects.filter(status='active').count()
        challenge_accounts = TradingAccount.objects.filter(account_type='challenge', status='active').count()
        funded_accounts = TradingAccount.objects.filter(account_type='funded', status='active').count()
        
        # Connection statistics
        connected_count = manager.connection_manager.get_connection_count()
        failed_count = len(manager.connection_manager.failed_connections)
        
        # Recent activity
        recent_activities = AccountActivity.objects.filter(
            timestamp__gte=datetime.now() - timedelta(hours=24)
        ).count()
        
        return {
            "database_stats": {
                "total_accounts": total_accounts,
                "active_accounts": active_accounts,
                "challenge_accounts": challenge_accounts,
                "funded_accounts": funded_accounts
            },
            "connection_stats": {
                "connected": connected_count,
                "failed": failed_count,
                "managed": len(manager.accounts),
                "known": len(manager.known_account_ids)
            },
            "activity_stats": {
                "recent_activities_24h": recent_activities
            },
            "manager_status": manager.get_status()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Disconnection failed: {str(e)}")

@app.get("/accounts/{account_id}/stats")
async def get_account_stats(account_id: str):
    """Get account statistics"""
    if account_id not in manager.accounts:
        raise HTTPException(status_code=404, detail="Account not found")
    
    account = manager.accounts[account_id]
    today_stats = await manager.get_or_create_daily_stats(account)
    
    return {
        "account_id": account_id,
        "daily_stats": {
            "date": today_stats.date.isoformat(),
            "starting_equity": float(today_stats.starting_equity),
            "current_equity": float(account.equity),
            "daily_pnl": float(today_stats.daily_pnl),
            "trades_count": today_stats.trades_count,
            "win_rate": float(today_stats.win_rate),
            "profit_factor": float(today_stats.profit_factor)
        }
    }

async def run_fastapi():
    """Run FastAPI server in background"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Main application entry point"""
    # Setup signal handlers
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(shutdown())
    
    if sys.platform != 'win32':
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)
    
    async def shutdown():
        """Graceful shutdown"""
        await manager.stop()
        # Cancel all running tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    
    try:
        # Start the manager
        await manager.start()
        
        # Start FastAPI server as background task
        fastapi_task = asyncio.create_task(run_fastapi())
        
        # Keep the main application running
        logger.info("Application is running. Press Ctrl+C to stop.")
        
        # Wait for shutdown signal
        try:
            await fastapi_task
        except asyncio.CancelledError:
            pass
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error in main: {e}")
    finally:
        await shutdown()
        logger.info("Application shutdown complete")

if __name__ == "__main__":
    try:
        # Verify required environment variables
        if not METAAPI_TOKEN:
            logger.error("METAAPI_TOKEN environment variable is required")
            sys.exit(1)
        
        # Run the main application
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)