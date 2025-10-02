import MT5Manager
from sub_manager.toDict import account_to_dict, position_to_dict
from stanum_web.tasks import *

class PositionSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
        if not self.bridge:
            print("Bridge is None inside OnPositionAdd!")

    def update_user_account(self, login):
        try:
            if self.bridge:
                account: MT5Manager.MTAccount = self.bridge.get_account(login)
                if account:
                    print(f"Retrieved Account info for {login}")
                    save_mt5_account.delay(account_to_dict(account))
                    return account
                else:
                    print(f"Failed to get account info for {login}")
        except Exception as err:
            print(f"Issue occured {str(err)}")

    # Add position
    def OnPositionAdd(self, position:MT5Manager.MTPosition):
        try:
            print(f"Position added: {position.Print()}")
            save_position.delay(position_to_dict(position))
            acc = self.update_user_account(position.Login)
            # if acc.challenge_completed or acc.challenge_failed:
            #     return
            if acc:
                self.bridge.update_memory_account(acc)
            self.bridge.add_memory_position(position)
        except Exception as err:
            print(f"Error Adding position {str(err)}")

    # Update position
    def OnPositionUpdate(self, position:MT5Manager.MTPosition):
        try:
            print(f"Position updated: {position.Print()}")
            save_position.delay(position_to_dict(position))
            acc = self.update_user_account(position.Login)
            # if acc and (acc.challenge_completed or acc.challenge_failed):
            #     return
            if acc:
                self.bridge.update_memory_account(acc)
            self.bridge.update_memory_position(position)
        except Exception as err:
            print(f"Error while updating position {str(err)}")

    # Delete Position
    def OnPositionDelete(self, position:MT5Manager.MTPosition):
        try:
            save_position.delay(position_to_dict(position))
            delete_position.delay(position_id=position.Position)
            acc = self.update_user_account(position.Login)
            # if acc.challenge_completed or acc.challenge_failed:
            #     return
            if acc:
                self.bridge.update_memory_account(acc)
            self.bridge.remove_memory_position(position)
            print(f"Position Deleted {position.Print()}")
        except Exception as err:
            print(f"Error while deleting position {str(err)}")

    
    # Clean user position
    def OnPositionClean(self, login):
        print(f"Position Cleaned {login}")
        clean_position.delay(login)
        account = self.update_user_account(login)
        if account:
            self.bridge.update_memory_account(account)