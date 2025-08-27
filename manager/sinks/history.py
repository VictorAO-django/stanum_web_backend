import MT5Manager
from trading.models import MT5OrderHistory

def save_mt5_order_history(order_obj:MT5Manager.MTOrder):
    """
    Save or update an MT5 order into Django database.
    order_obj: IMTOrder object from MT5 Manager API
    """
    order, _ = MT5OrderHistory.objects.update_or_create(
        order=order_obj.Order,
        defaults=dict(
            external_id=getattr(order_obj, "ExternalID", None),
            login=getattr(order_obj, "Login", None),
            dealer=getattr(order_obj, "Dealer", None),
            symbol=getattr(order_obj, "Symbol", None),

            digits=getattr(order_obj, "Digits", 0),
            digits_currency=getattr(order_obj, "DigitsCurrency", 0),
            contract_size=getattr(order_obj, "ContractSize", 0),

            state=getattr(order_obj, "State", None),
            reason=getattr(order_obj, "Reason", None),

            time_setup=getattr(order_obj, "TimeSetup", None),
            time_setup_msc=getattr(order_obj, "TimeSetupMsc", None),
            time_expiration=getattr(order_obj, "TimeExpiration", None),
            time_done=getattr(order_obj, "TimeDone", None),
            time_done_msc=getattr(order_obj, "TimeDoneMsc", None),

            type=getattr(order_obj, "Type", None),
            type_fill=getattr(order_obj, "TypeFill", None),
            type_time=getattr(order_obj, "TypeTime", None),

            price_order=getattr(order_obj, "PriceOrder", 0),
            price_trigger=getattr(order_obj, "PriceTrigger", 0),
            price_current=getattr(order_obj, "PriceCurrent", 0),
            price_sl=getattr(order_obj, "PriceSL", 0),
            price_tp=getattr(order_obj, "PriceTP", 0),

            volume_initial=getattr(order_obj, "VolumeInitial", 0),
            volume_initial_ext=getattr(order_obj, "VolumeInitialExt", 0),
            volume_current=getattr(order_obj, "VolumeCurrent", 0),
            volume_current_ext=getattr(order_obj, "VolumeCurrentExt", 0),

            expert_id=getattr(order_obj, "ExpertID", None),
            position_id=getattr(order_obj, "PositionID", None),
            position_by_id=getattr(order_obj, "PositionByID", None),
            comment=getattr(order_obj, "Comment", None),

            activation_mode=getattr(order_obj, "ActivationMode", None),
            activation_time=getattr(order_obj, "ActivationTime", None),
            activation_price=getattr(order_obj, "ActivationPrice", 0),
            activation_flags=getattr(order_obj, "ActivationFlags", 0),

            rate_margin=getattr(order_obj, "RateMargin", 0),
            modification_flags=getattr(order_obj, "ModificationFlags", 0),
        )
    )
    return order


class OrderHistorySink:
    def OnHistoryAdd(self, order:MT5Manager.MTOrder):
        order.Print()
        save_mt5_order_history(order)

    def OnHistoryUpdate(self, order:MT5Manager.MTOrder):
        order.Print()
        save_mt5_order_history(order)

    def OnHistoryDelete(self, order:MT5Manager.MTOrder):
        order.Print()
        MT5OrderHistory.objects.filter(order=order.Order).delete()

    def OnHistoryClean(self, login):
        MT5OrderHistory.objects.filter(login=login).delete()
    