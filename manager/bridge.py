import os, dotenv, logging, time
import MT5Manager

from .sinks.position import PositionSink
from .sinks.deal import DealSink
from .sinks.user import UserSink
from .sinks.order import OrderSink
from .sinks.account import AccountSink
from .sinks.summary import SummarySink
from .sinks.daily import DailySink

dotenv.load_dotenv()
logger = logging.getLogger(__name__)


class MetaTraderBridge:
    def __init__(self, address, login, password, user_group):
        self.address = address
        self.login = int(login)
        self.password = password
        self.user_group = user_group
        self.manager = MT5Manager.ManagerAPI()

    def connect(self):
        self._subscribe_sinks()
        connected = self.manager.Connect(
            self.address,
            self.login,
            self.password,
            MT5Manager.ManagerAPI.EnPumpModes.PUMP_MODE_FULL
        )

        if not connected:
            logger.error(f"Failed to connect: {MT5Manager.LastError()}")
            return False

        logger.info("Connected to MT5 Manager API")
        
        return True

    def disconnect(self):
        logger.info("Disconnecting from MT5...")
        return self.manager.Disconnect()

    def _subscribe_sinks(self):
        """Subscribe to all data sinks"""
        if not self.manager.UserSubscribe(UserSink()):
            logger.error(f"UserSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.PositionSubscribe(PositionSink()):
            logger.error(f"PositionSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.DealSubscribe(DealSink()):
            logger.error(f"DealSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.OrderSubscribe(OrderSink()):
            logger.error(f"OrderSubscribe failed: {MT5Manager.LastError()}")

        if not self.manager.UserAccountSubscribe(AccountSink()):
            logger.error(f"AccountSubscribe failed: {MT5Manager.LastError()}")

        # if not self.manager.SummarySubscribe(SummarySink()):
        #     logger.error(f"SummarySubscribe failed: {MT5Manager.LastError()}")

        # if not self.manager.DailySubscribe(DailySink()):
        #     logger.error(f"DailySubscribe failed: {MT5Manager.LastError()}")

        logger.info("All sinks subscribed successfully")
