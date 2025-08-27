import asyncio, os, dotenv, signal, logging, string, secrets, django, datetime, MT5Manager 
from typing import List
from .interface import NewAccountData
from trading.models import MT5Account
from .sinks.user import save_mt5_user

class MT5AccountService:
    def __init__(self, address, login, password, user_group):
        self.address = address
        self.login = login
        self.password = password
        self.user_group = user_group
        self.manager = MT5Manager.ManagerAPI()
        pass
    
    def connect(self):
        return self.manager.Connect( self.address, self.login, self.password, MT5Manager.ManagerAPI.EnPumpModes.PUMP_MODE_USERS)

    def disconnect(self):
        return self.manager.Disconnect()
        
    def createUser(self, data: NewAccountData):
        # create a user 
        user = MT5Manager.MTUser(self.manager) 
        # fill in the required fields: group, leverage, first and last name 
        user.Group = self.user_group 
        user.Leverage = 100 
        user.FirstName = data.first_name
        user.LastName = data.last_name
        user.Country = data.country
        user.Company = data.company
        user.EMail = data.email
        user.Phone = data.phone
        user.ZIPCode = data.zip_code
        user.State = data.state
        user.City = data.city
        user.Address = data.address
        user.Language = data.language
        user.Comment = data.comment

        master_password = self.gen_master_password()
        investor_password = self.gen_investor_password()

        # add a user to the server 
        if not self.manager.UserAdd(user, master_password, investor_password): 
            # adding failed with an error 
            error = MT5Manager.LastError() 
            # no more logins 
            if error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_USR_LOGIN_EXHAUSTED: 
                print("No free logins on server") 
            # add a user to another server 
            elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_USR_LOGIN_PROHIBITED: 
                print("Can't add user for non current server") 
            # such a user already exists 
            elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_USR_LOGIN_EXIST: 
                print("User with same login already exists") 
            # another error 
            else: 
                print(f"User was not added: {MT5Manager.LastError()}") 
        else: 
            # user added successfully 
            print(f"User {user.Login} was added") 
            # deposit balance 
            deal_id = self.manager.DealerBalance(user.Login, data.balance, MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE, "Start deposit") 
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
                # make sure the balance deposited 
                user = self.manager.UserRequest(user.Login) 
                # user not found 
                if user == False: 
                    print(f"Failed to request user: {MT5Manager.LastError()}") 
                else: 
                    # display user balance 
                    print(f"Found user {user.Login}, balance: {user.Balance}") 
                # update user rights 
                user.Rights = MT5Manager.MTUser.EnUsersRights.USER_RIGHT_ENABLED | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_PASSWORD | MT5Manager.MTUser.EnUsersRights.USER_RIGHT_EXPERT 
                # update user on server 
                if not self.manager.UserUpdate(user): 
                    print(f"Failed to update user: {MT5Manager.LastError()}") 
                else: 
                    # change user password 
                    if not self.manager.UserPasswordChange(
                        MT5Manager.MTUser.EnUsersPasswords.USER_PASS_MAIN, 
                        user.Login, 
                        master_password
                    ): 
                        print(f"Failed to update user password: {MT5Manager.LastError()}") 

            mt5_user = save_mt5_user(user)
            return (mt5_user, master_password)
        


    def list_users(self) -> List[MT5Manager.MTUser]:
        users = self.manager.UserGetByGroup(self.user_group)  
        return users  

    def get_user(self, login)->MT5Manager.MTUser:
       return self.manager.UserGet(login)
    
    def deposit_balance(self, login, amount):
        deal_id = self.manager.DealerBalance(login, amount,MT5Manager.MTDeal.EnDealAction.DEAL_BALANCE,"Start deposit from stanum admin")
        if deal_id is False: 
            # depositing ended with error 
            error = MT5Manager.LastError() 
            # too much deposit amount 
            if error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_TRADE_MAX_MONEY: 
                return (False, "Money limit") 
            # insufficient money on the account 
            elif error[1] == MT5Manager.EnMTAPIRetcode.MT_RET_REQUEST_NO_MONEY: 
                return(False, "Not enough money") 
            # another error 
            else: 
                return (False, f"Balance operation failed {MT5Manager.LastError()}")
        return (True, "success")
    

    def gen_master_password(self, length: int = 8) -> str:
        """Generate a secure master password (full access)."""
        alphabet = string.ascii_letters + string.digits + string.punctuation
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def gen_investor_password(self, length: int = 8) -> str:
        """Generate a secure investor password (read-only)."""
        alphabet = string.ascii_letters + string.digits  # simpler, no punctuation
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    