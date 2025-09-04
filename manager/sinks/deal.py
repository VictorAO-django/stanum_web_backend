import MT5Manager
from trading.models import MT5Deal
from manager.rule_checker import RuleChecker
import logging
from .account import save_mt5_account

logger = logging.getLogger(__name__)

def save_mt5_deal(deal_obj: MT5Manager.MTDeal):
    deal, _ = MT5Deal.objects.update_or_create(
        deal=deal_obj.Deal,  # unique ticket
        defaults=dict(
            external_id=getattr(deal_obj, "ExternalID", None),
            login=getattr(deal_obj, "Login", None),
            dealer=getattr(deal_obj, "Dealer", None),
            order=getattr(deal_obj, "Order", None),
            action=getattr(deal_obj, "Action", None),
            entry=getattr(deal_obj, "Entry", None),
            digits=getattr(deal_obj, "Digits", 0),
            digits_currency=getattr(deal_obj, "DigitsCurrency", 0),
            contract_size=getattr(deal_obj, "ContractSize", 0),
            time=getattr(deal_obj, "Time", None),
            time_msc=getattr(deal_obj, "TimeMsc", None),
            symbol=getattr(deal_obj, "Symbol", None),
            price=getattr(deal_obj, "Price", 0),
            price_sl=getattr(deal_obj, "PriceSL", 0),
            price_tp=getattr(deal_obj, "PriceTP", 0),
            price_position=getattr(deal_obj, "PricePosition", 0),
            volume=getattr(deal_obj, "Volume", 0),
            volume_ext=getattr(deal_obj, "VolumeExt", 0),
            volume_closed=getattr(deal_obj, "VolumeClosed", 0),
            volume_closed_ext=getattr(deal_obj, "VolumeClosedExt", 0),
            profit=getattr(deal_obj, "Profit", 0),
            profit_raw=getattr(deal_obj, "ProfitRaw", 0),
            value=getattr(deal_obj, "Value", 0),
            storage=getattr(deal_obj, "Storage", 0),
            commission=getattr(deal_obj, "Commission", 0),
            fee=getattr(deal_obj, "Fee", 0),
            rate_profit=getattr(deal_obj, "RateProfit", 0),
            rate_margin=getattr(deal_obj, "RateMargin", 0),
            expert_id=getattr(deal_obj, "ExpertID", None),
            position_id=getattr(deal_obj, "PositionID", None),
            comment=getattr(deal_obj, "Comment", None),
            tick_value=getattr(deal_obj, "TickValue", 0),
            tick_size=getattr(deal_obj, "TickSize", 0),
            flags=getattr(deal_obj, "Flags", 0),
            reason=getattr(deal_obj, "Reason", None),
            gateway=getattr(deal_obj, "Gateway", None),
            price_gateway=getattr(deal_obj, "PriceGateway", 0),
            volume_gateway_ext=getattr(deal_obj, "VolumeGatewayExt", 0),
            action_gateway=getattr(deal_obj, "ActionGateway", None),
            market_bid=getattr(deal_obj, "MarketBid", 0),
            market_ask=getattr(deal_obj, "MarketAsk", 0),
            market_last=getattr(deal_obj, "MarketLast", 0),
            modification_flags=getattr(deal_obj, "ModificationFlags", 0),
        )
    )
    return deal


class DealSink:
    def __init__(self, bridge=None):
        self.bridge = bridge
        self.rule_checker = RuleChecker()
    
    def OnDealAdd(self, deal: MT5Manager.MTDeal):
        try:
            print("Deal Added", deal.Print())
            save_mt5_deal(deal)
        except Exception as err:
            print("Error Adding deal", str(err))
    
    def OnDealUpdate(self, deal: MT5Manager.MTDeal):
        print("Deal Updated", deal.Print())
        # Save updated deal to database
        save_mt5_deal(deal)

    def OnDealDelete(self, deal: MT5Manager.MTDeal):
        print("Deal Deleted", deal.Print())
        MT5Deal.objects.filter(deal=deal.Deal).update(deleted=True)
        print(f"Deal {deal.Deal} deleted from database")
    
    def OnDealClean(self, login):
        print("Deal Clean", login)
        deleted_count, _ = MT5Deal.objects.filter(login=login).update(deleted=True)
        print(f"Cleaned {deleted_count} deals for login {login}")