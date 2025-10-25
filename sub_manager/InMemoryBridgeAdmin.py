import MT5Manager, traceback, json
from typing import List
from confluent_kafka import Consumer, Producer
from sub_manager.logging_config import get_prop_logger
from django.conf import settings
logger = get_prop_logger('monitoring')

class MetaTraderBridge:
    def __init__(self, address, login, password, user_group):
        self.address = address
        self.login = int(login)
        self.password = password
        self.user_group = user_group
        self.manager = MT5Manager.ManagerAPI()
        # self.in_memory_monitor = None
        self.count = 0

    def connect(self):
        connected = self.manager.Connect(
            self.address,
            self.login,
            self.password,
            MT5Manager.ManagerAPI.EnPumpModes.PUMP_MODE_FULL
        )

        if not connected:
            print(f"Failed to connect: {MT5Manager.LastError()}")
            return False

        logger.info("Connected to MT5 Manager API")
        return True
    
    def disconnect(self):
        logger.info("Disconnecting from MT5...")
        return self.manager.Disconnect()
    
    def get_user(self, login)->MT5Manager.MTUser:
       return self.manager.UserGet(login)
    
    def get_account(self, login)->MT5Manager.MTAccount:
        return self.manager.UserAccountGet(login)
    
    def disable_challenge_account_trading(self, login):
        try:
            logger.info(f"Requesting for user detail", login)
            user = self.manager.UserRequest(login) 

            # user not found 
            if user == False: 
                print(f"Failed to request user: {MT5Manager.LastError()}") 
            else: 
                # display user balance 
                print(f"Found user {user.Login}, balance: {user.Balance}") 
            # update user rights 
            user.Rights = 0
            if not self.manager.UserUpdate(user): 
                print(f"Failed to update user: {MT5Manager.LastError()}") 

            # account = self.get_account(login)
            # save_mt5_account(account)
            # self._close_all_positions(login)

        except Exception as err:
            print(f"Error disabling account {str(err)}")

    def enable_account_trading(self, login):
        try:
            user = self.manager.UserRequest(login) 

            # user not found 
            if user == False: 
                print(f"Failed to request user: {MT5Manager.LastError()}") 
            else: 
                # display user balance 
                print(f"Found user {user.Login}, balance: {user.Balance}") 
            # update user rights 
            user.Rights = MT5Manager.MTUser.EnUsersRights.USER_RIGHT_ENABLED | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_PASSWORD | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_EXPERT 
            if not self.manager.UserUpdate(user): 
                print(f"Failed to update user: {MT5Manager.LastError()}") 

        except Exception as err:
            print(f"Error enabling account {str(err)}")


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
                    print("Money limit") 
                # insufficient money on the account 
                elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_REQUEST_NO_MONEY: 
                    print("Not enough money") 
                # another error 
                else: 
                    print(f"Balance operation failed {MT5Manager.LastError()}") 
            else: 
                # balance deposited successfully 
                print(f"Balance operation succeeded")

        except Exception as err:
            print(f"Error replenishing account balance - {str(err)}")
    
    def update_account_balance(self, login, amount_to_add):
        try:
            amount_to_add = float(amount_to_add)
            deal_id = self.manager.DealerBalance(login, amount_to_add, MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE, f"Added {amount_to_add} to balance ") 
            if deal_id is False: 
                # depositing ended with error 
                error = MT5Manager.LastError() 
                # too much deposit amount 
                if error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_TRADE_MAX_MONEY: 
                    print("Money limit") 
                # insufficient money on the account 
                elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_REQUEST_NO_MONEY: 
                    print("Not enough money") 
                # another error 
                else: 
                    print(f"Balance operation failed {MT5Manager.LastError()}") 
            else: 
                # balance deposited successfully 
                print(f"Balance operation succeeded")

        except Exception as err:
            print(f"Error replenishing account balance - {str(err)}")

    def get_positions(self, login)->List[MT5Manager.MTPosition]:
        return self.manager.PositionGet(login)
    
    def close_all_positions(self, login: int):
        """Close all open positions for an account"""
        try:
            print("attempting to retrieve account positions")
            # Get all open positions
            positions = self.get_positions(login)
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

    

bridge = MetaTraderBridge(
    address=settings.METATRADER_SERVER,
    login=settings.METATRADER_LOGIN,
    password=settings.METATRADER_PASSWORD,
    user_group=settings.METATRADER_USERGROUP,
)
bridge.connect()

c = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": "rule-engine",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": True,
    "auto.commit.interval.ms": 5000
})

c.subscribe([
    "disable_trading", "enable_trading", "return_balance", "update_balance", "close_positions",
    "account.fund"
])

while True:
    msg = c.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("Error:", msg.error())
        continue
    
    try:
        # logger.info(msg.topic(), msg.value())
        if msg.topic() == "disable_trading":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            bridge.disable_challenge_account_trading(int(login))

        elif msg.topic() == "enable_trading":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            bridge.enable_account_trading(int(login))
        
        elif msg.topic() == "account.fund":
            data = json.loads(msg.value().decode("utf-8"))
            login=int(data['login'])
            bridge.enable_account_trading(int(login))

        elif msg.topic() == "return_balance":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            initial_balance=data['initial_balance']
            bridge.return_account_balance(int(login), float(initial_balance))

        elif msg.topic() == "update_balance":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            amount_to_add=data['amount_to_add']
            bridge.update_account_balance(int(login), float(amount_to_add))

        elif msg.topic() == "close_positions":
            data = json.loads(msg.value().decode("utf-8"))
            login=data['login']
            bridge.close_all_positions(int(login))
        
    except Exception as err:
        print(f"ERROR OCCURED: {str(err)}")
        traceback.print_exc()