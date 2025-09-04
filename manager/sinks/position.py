import MT5Manager
from datetime import datetime
from django.utils import timezone
from trading.models import MT5Position
from .account import save_mt5_account
from manager.rule_checker import *

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
        self.rule_checker = RuleChecker()

    def update_user_account(self, position:MT5Manager.MTPosition):
        print("Reached here")
        if self.bridge:
            account: MT5Manager.MTAccount = self.bridge.get_account(position.Login)
            if account:
                print(f"Retrieved Account info for {position.Login}")
                save_mt5_account(account)
                # Check trading rules
                violations = self.rule_checker.check_position_rules(position, account)
                # Handle position violations through bridge
                if violations and self.bridge:
                    self.bridge.handle_violation(position.Login, violations, "POSITION")
                    print("Violations detected", violations)
                elif violations:
                    # Fallback logging if bridge not available
                    print(f"Violations detected for {position.Login} but no bridge available: {violations}")
            else:
                print(f"Failed to get account info for {position.Login}")
        print("Reached here also")

    # Add position
    def OnPositionAdd(self, position:MT5Manager.MTPosition):
        try:
            print(f"Position added: {position.Print()}")
            save_position(position)
            self.update_user_account(position)
        except Exception as err:
            print("Error Adding position", str(err))

    # Update position
    def OnPositionUpdate(self, position:MT5Manager.MTPosition):
        print(f"Position updated: {position.Print()}")
        # Update existing entry
        save_position(position)
        self.update_user_account(position.Login)

    # Delete Position
    def OnPositionDelete(self, position:MT5Manager.MTPosition):
        print(f"Position Deleted", position.Print())
        pos = MT5Position.objects.filter(position_id=position.Position)
        if pos.exists():
            pos = pos.first()
            pos.closed = True
            pos.save()
        self.update_user_account(position.Login)
    
    # Clean user position
    def OnPositionClean(self, login):
        print(f"Position Cleaned", login)
        MT5Position.objects.filter(login=login).delete()
        self.update_user_account(login)
