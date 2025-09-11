import MT5Manager
from datetime import datetime
from django.utils import timezone
from trading.models import MT5Position
from .account import save_mt5_account

def save_position(position: MT5Manager.MTPosition):
    """Save or update MT5Position with create/update logic"""
    
    def convert_time(epoch):
        if not epoch:
            return None
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    
    # Prepare position data
    position_data = {
        'login': position.Login,
        'symbol': position.Symbol,
        'comment': position.Comment,
        'price_open': position.PriceOpen,
        'price_current': position.PriceCurrent,
        'price_sl': position.PriceSL,
        'price_tp': position.PriceTP,
        'price_gateway': position.PriceGateway,
        'volume': position.Volume,
        'volume_ext': position.VolumeExt,
        'volume_gateway_ext': position.VolumeGatewayExt,
        'profit': position.Profit,
        'storage': position.Storage,
        'contract_size': position.ContractSize,
        'rate_margin': position.RateMargin,
        'rate_profit': position.RateProfit,
        'expert_id': position.ExpertID,
        'expert_position_id': position.ExpertPositionID,
        'dealer': position.Dealer,
        'external_id': position.ExternalID,
        'time_create': convert_time(position.TimeCreate),
        'time_update': convert_time(position.TimeUpdate),
        'action': position.Action,
        'reason': position.Reason,
        'digits': position.Digits,
        'digits_currency': position.DigitsCurrency,
        'obsolete_value': position.ObsoleteValue,
        'activation_flags': position.ActivationFlags,
        'activation_mode': position.ActivationMode,
        'activation_price': position.ActivationPrice,
        'activation_time': position.ActivationTime,
    }
    
    # Create or update position
    mt5_position, created = MT5Position.objects.update_or_create(
        position_id=position.Position,
        defaults=position_data
    )
    
    return mt5_position, created

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
                    return save_mt5_account(account)
                else:
                    print(f"Failed to get account info for {login}")
        except Exception as err:
            print(f"Issue occured {str(err)}")

    # Add position
    def OnPositionAdd(self, position:MT5Manager.MTPosition):
        try:
            print(f"Position added: {position.Print()}")
            pos, _ = save_position(position)
            acc = self.update_user_account(position.Login)

            if acc.challenge_completed or acc.challenge_failed:
                return
            self.bridge.update_memory_account(acc)
            self.bridge.add_memory_position(pos)
        except Exception as err:
            print(f"Error Adding position {str(err)}")

    # Update position
    def OnPositionUpdate(self, position:MT5Manager.MTPosition):
        try:
            print(f"Position updated: {position.Print()}")
            pos, _ = save_position(position)
            acc = self.update_user_account(position.Login)
            if acc and (acc.challenge_completed or acc.challenge_failed):
                return
            self.bridge.update_memory_account(acc)
            self.bridge.update_memory_position(pos)
        except Exception as err:
            print(f"Error while updating position {str(err)}")

    # Delete Position
    def OnPositionDelete(self, position:MT5Manager.MTPosition):
        try:
            pos = MT5Position.objects.filter(position_id=position.Position)
            if pos.exists():
                pos = pos.first()
                pos.closed = True
                pos.save()
            acc = self.update_user_account(position.Login)
            if acc.challenge_completed or acc.challenge_failed:
                return
            self.bridge.update_memory_account(acc)
            self.bridge.remove_memory_position(pos)
            print(f"Position Deleted {position.Print()}")
        except Exception as err:
            print(f"Error while deleting position {str(err)}")

    
    # Clean user position
    def OnPositionClean(self, login):
        print(f"Position Cleaned {login}")
        MT5Position.objects.filter(login=login).update(closed=True)
        self.update_user_account(login)
