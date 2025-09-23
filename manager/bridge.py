import os, dotenv, logging, time
import MT5Manager
from .sinks.position import PositionSink
from .sinks.deal import DealSink
from .sinks.user import UserSink
from .sinks.order import OrderSink
from .sinks.account import AccountSink, save_mt5_account
from .sinks.summary import SummarySink
from .sinks.daily import DailySink
from .sinks.tick import TickSink
from trading.models import MT5User, RuleViolationLog, MT5Position, MT5Account, MT5Deal
from challenge.models import PropFirmChallenge
from datetime import datetime, timedelta
from django.utils import timezone
from collections import defaultdict
from enum import Enum
from typing import List, Dict
from .InMemoryPropMonitoring import InMemoryPropMonitoring

from .logging_config import get_prop_logger
logger = get_prop_logger('bridge')

dotenv.load_dotenv()
logger = logging.getLogger(__name__)

class MetaTraderBridge:
    def __init__(self, address, login, password, user_group):
        self.address = address
        self.login = int(login)
        self.password = password
        self.user_group = user_group
        self.manager = MT5Manager.ManagerAPI()
        self.in_memory_monitor = InMemoryPropMonitoring(self)

    def connect(self):
        self._subscribe_sinks()
        connected = self.manager.Connect(
            self.address,
            self.login,
            self.password,
            MT5Manager.ManagerAPI.EnPumpModes.PUMP_MODE_FULL
        )

        if not connected:
            logger.debug(f"Failed to connect: {MT5Manager.LastError()}")
            return False

        logger.info("Connected to MT5 Manager API")
        return True

    def disconnect(self):
        logger.info("Disconnecting from MT5...")
        return self.manager.Disconnect()

    def _subscribe_sinks(self):
        """Subscribe to all data sinks with bridge reference"""
        if not self.manager.UserSubscribe(UserSink()):
            logger.debug(f"UserSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.PositionSubscribe(PositionSink(self)):
            logger.debug(f"PositionSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.DealSubscribe(DealSink(self)):
            logger.debug(f"DealSubscribe failed: {MT5Manager.LastError()}")

        # if not self.manager.OrderSubscribe(OrderSink()):
        #     logger.debug(f"OrderSubscribe failed: {MT5Manager.LastError()}")

        # if not self.manager.UserAccountSubscribe(AccountSink(self)):
        #     logger.debug(f"AccountSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.TickSubscribe(TickSink(self)):
            logger.debug(f"TickSubscribe failed: {MT5Manager.LastError()}")

        logger.info("All sinks subscribed successfully")

    def get_user(self, login)->MT5Manager.MTUser:
       return self.manager.UserGet(login)
    
    def delete_user(self, login)->MT5Manager.MTUser:
        return self.manager.UserDelete(login)
    
    def get_account(self, login)->MT5Manager.MTAccount:
        return self.manager.UserAccountGet(login)
    
    def _close_all_positions(self, login: int):
        """Close all open positions for an account"""
        try:
            print("attempting to retrieve account positions")
            # Get all open positions
            positions = self.manager.PositionGet(login)
            print("Positions retrieved", positions)
            for position in positions:
                print(f"Attending to {position.Position}")
                result = self.manager.PositionDelete(position)
                print("Reached here")
                if not result:
                    print(f"Failed to close position {position.Position}")
                print(MT5Manager.LastError())
        except Exception as e:
            print(f"Error closing positions for {login}: {e}")

    def disable_challenge_account_trading(self, login):
        try:
            logger.info(f"Requesting for user detail", login)
            user = self.manager.UserRequest(login) 

            # user not found 
            if user == False: 
                logger.debug(f"Failed to request user: {MT5Manager.LastError()}") 
            else: 
                # display user balance 
                logger.info(f"Found user {user.Login}, balance: {user.Balance}") 
            # update user rights 
            user.Rights = 0
            if not self.manager.UserUpdate(user): 
                logger.debug(f"Failed to update user: {MT5Manager.LastError()}") 

            # account = self.get_account(login)
            # save_mt5_account(account)
            # self._close_all_positions(login)

        except Exception as err:
            logger.debug(f"Error disabling account {str(err)}")

    def enable_account_trading(self, login):
        try:
            user = self.manager.UserRequest(login) 

            # user not found 
            if user == False: 
                logger.debug(f"Failed to request user: {MT5Manager.LastError()}") 
            else: 
                # display user balance 
                logger.info(f"Found user {user.Login}, balance: {user.Balance}") 
            # update user rights 
            user.Rights = MT5Manager.MTUser.EnUsersRights.USER_RIGHT_ENABLED | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_PASSWORD | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_EXPERT 
            if not self.manager.UserUpdate(user): 
                logger.debug(f"Failed to update user: {MT5Manager.LastError()}") 

            account = self.get_account(login)
            save_mt5_account(account)

        except Exception as err:
            logger.debug(f"Error enabling account {str(err)}")


    def return_account_balance(self, login, initial_balance):
        try:
            account = self.get_account(login)
            current_balance = float(account.Balance)
            adjustment = float(initial_balance) - current_balance

            if adjustment == 0:
                return {"success": True, "message": "Account already at initial balance"}
        
            deal_id = self.manager.DealerBalance(login, float(adjustment), MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE, f"Reset balance to initial {initial_balance}") 
            if deal_id is False: 
                # depositing ended with error 
                error = MT5Manager.LastError() 
                # too much deposit amount 
                if error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_TRADE_MAX_MONEY: 
                    logger.debug("Money limit") 
                # insufficient money on the account 
                elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_REQUEST_NO_MONEY: 
                    logger.debug("Not enough money") 
                # another error 
                else: 
                    logger.debug(f"Balance operation failed {MT5Manager.LastError()}") 
            else: 
                # balance deposited successfully 
                logger.info(f"Balance operation succeeded")

        except Exception as err:
            logger.debug(f"Error replenishing account balance - {str(err)}")

    def reset_account(self, login, initial_balance):
        try:
            print(f"Account reset begins {login}")
            self._close_all_positions(login)
            self.return_account_balance(login, initial_balance)
            print(f"Account reset successful")
        except Exception as err:
            print(f"Failed to reset account {str(err)}")

    def tick(self, symbol, tick:MT5Manager.MTTick):
        self.in_memory_monitor.OnTick(symbol, tick)

    def add_memory_position(self, position:MT5Position):
        logger.info(f"calling Bridge Add position {position.login}")
        self.in_memory_monitor.add_position(position)
    
    def update_memory_position(self, position:MT5Position):
        logger.info(f"calling Bridge Update position {position.login}")
        self.in_memory_monitor.update_position(position)

    def remove_memory_position(self, position:MT5Position):
        logger.info(f"calling Bridge Remove position {position.login}")
        self.in_memory_monitor.remove_position(position)

    def add_memory_deal(self, deal:MT5Deal):
        logger.info(f"calling Bridge Add deal {deal.login}")
        self.in_memory_monitor.add_deal(deal)
    
    def update_memory_deal(self, deal:MT5Deal):
        logger.info(f"calling Bridge Update deal {deal.login}")
        self.in_memory_monitor.update_deal(deal)

    def remove_memory_deal(self, deal:MT5Deal):
        logger.info(f"calling Bridge Remove deal {deal.login}")
        self.in_memory_monitor.remove_deal(deal)

    def update_memory_account(self, account:MT5Account):
        logger.info(f"calling Bridge Update Account {account.login}")
        self.in_memory_monitor.update_account(account)
    
    def add_memory_account(self, account:MT5Account):
        logger.info(f"calling Bridge Add Account {account.login}")
        self.in_memory_monitor.add_account(account)

    def periodic_cleanup(self):
        logger.info("Cleaning up...")
        self.in_memory_monitor.cleanup_unused_symbols()
        logger.info("Done cleaning up")

