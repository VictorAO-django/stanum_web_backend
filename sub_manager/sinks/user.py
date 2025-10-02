import MT5Manager
from trading.models import MT5User, MT5Deal, MT5Position, MT5UserLoginHistory
from datetime import datetime
from utils.helper import encrypt_password
from stanum_web.tasks import *
from sub_manager.toDict import account_to_dict, user_to_dict

class UserSink: 
    def __init__(self, bridge=None):
        self.bridge = bridge

    def update_user_account(self, login):
        try:
            if self.bridge:
                account = self.bridge.get_account(login)
                if account:
                    print(f"Retrieved Account info for {login}")
                    save_mt5_account.delay(account_to_dict(account))
                    self.bridge.update_memory_account(account)
                else:
                    print(f"Failed to get account info for {login}")
        except Exception as err:
            print(f"Error when updating account {str(err)}")

    def OnUserDelete(self, user:MT5Manager.MTUser) -> None: 
        print(f"User with login: {user.Login} was deleted")
    
    def OnUserAdd(self, user:MT5Manager.MTUser):
        try:
            print("User added", user.Login)
            save_mt5_user.delay(user_to_dict(user))
            self.update_user_account(user.Login)
        except Exception as err:
            print("Error adding user", str(err))

    def OnUserUpdate(self, user:MT5Manager.MTUser):
        try:
            print("User updated", user.Login)
            save_mt5_user.delay(user_to_dict(user))
            self.update_user_account(user.Login)
        except Exception as err:
            print("Error updating user", str(err))

    def OnUserLogin(ip:str, user:MT5Manager.MTUser, type):
        user_login.delay(ip, user, type)

    def OnUserLogout(ip:str, user:MT5Manager.MTUser, type):
        user_logout.delay(ip, user, type)

    def OnUserChangePassword(user:MT5Manager.MTUser, type:MT5Manager.MTUser.EnUsersPasswords, password):
        if type == MT5Manager.MTUser.EnUsersPasswords.USER_PASS_API:
            change_password.delay(user.Login, password)