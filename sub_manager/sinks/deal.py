import MT5Manager, traceback
from trading.models import MT5Deal
import logging
from stanum_web.tasks import *
from sub_manager.toDict import account_to_dict, deal_to_dict

logger = logging.getLogger(__name__)

class DealSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
    
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
                    return None
        except Exception as err:
            print(f"Issue occured {str(err)}")
            
    def OnDealAdd(self, deal: MT5Manager.MTDeal):
        try:
            print("Deal Added", deal.Print())
            save_mt5_deal.delay(deal_to_dict(deal))
            acc = self.update_user_account(deal.Login)
            if acc:
                # if(acc.challenge_completed or acc.challenge_failed):
                #     return
                self.bridge.update_memory_account(acc)
            self.bridge.add_memory_deal(deal)
        except Exception as err:
            print("Error Adding deal", str(err))
            traceback.print_exc()
    
    def OnDealUpdate(self, deal: MT5Manager.MTDeal):
        try:
            print("Deal Updated", deal.Print())
            # Save updated deal to database
            mt5_deal = save_mt5_deal.delay(deal_to_dict(deal))
            acc = self.update_user_account(deal.Login)
            if acc:
                # if(acc.challenge_completed or acc.challenge_failed):
                #     return
                self.bridge.update_memory_account(acc)
            self.bridge.update_memory_deal(mt5_deal)
        except Exception as err:
            print("Error Updating deal", str(err))
            traceback.print_exc()

    def OnDealDelete(self, deal: MT5Manager.MTDeal):
        try:
            print("Deal Deleted", deal.Print())
            save_mt5_deal.delay(deal_to_dict(deal))
            delete_deal.delay(deal.Deal)
            self.bridge.remove_memory_deal(deal)
            print(f"Deal {deal.Deal} deleted from database")
        except Exception as err:
            print("Error Adding deal", str(err))
            traceback.print_exc()
        
    
    def OnDealClean(self, login):
        print("Deal Clean", login)
        deleted_count, _ = MT5Deal.objects.filter(login=login).update(deleted=True)
        print(f"Cleaned {deleted_count} deals for login {login}")