import MT5Manager 
import asyncio, os, dotenv, signal, logging, string, secrets, django, datetime
from typing import List
from django.utils import timezone
import datetime
from trading.models import MT5Position


class PositionSink:
    # Add position
    def OnPositionAdd(self, position:MT5Manager.MTPosition):
        print(f"Position added: {position.Print()}")
        # Convert MT5 timestamps (epoch) to Python datetime
        def convert_time(epoch):
            if not epoch:
                return None
            return datetime.datetime.fromtimestamp(epoch, tz=timezone.utc)
        # Save to Django model
        MT5Position.objects.create(
            position_id=position.Position, login=position.Login, symbol=position.Symbol, comment=position.Comment,
            price_open=position.PriceOpen, price_current=position.PriceCurrent, price_sl=position.PriceSL, price_tp=position.PriceTP, price_gateway=position.PriceGateway,
            volume=position.Volume, volume_ext=position.VolumeExt, volume_gateway_ext=position.VolumeGatewayExt,
            profit=position.Profit, storage=position.Storage, contract_size=position.ContractSize, rate_margin=position.RateMargin, rate_profit=position.RateProfit,
            expert_id=position.ExpertID, expert_position_id=position.ExpertPositionID, dealer=position.Dealer, external_id=position.ExternalID,
            time_create=convert_time(position.TimeCreate), time_update=convert_time(position.TimeUpdate),
            action=position.Action, reason=position.Reason, digits=position.Digits, digits_currency=position.DigitsCurrency,
            obsolete_value=position.ObsoleteValue, activation_flags=position.ActivationFlags, activation_mode=position.ActivationMode,
            activation_price=position.ActivationPrice,activation_time=position.ActivationTime,
        )

    # Update position
    def OnPositionUpdate(self, position:MT5Manager.MTPosition):
        print(f"Position updated: {position.Print()}")
        # Update existing entry
        MT5Position.objects.filter(position_id=position.Position).update(
            price_current=position.PriceCurrent, profit=position.Profit, volume=position.Volume, price_sl=position.PriceSL, 
            price_tp=position.PriceTP, time_update=datetime.datetime.fromtimestamp(position.TimeUpdate, tz=timezone.utc)
        )

    # Delete Position
    def OnPositionDelete(self, position:MT5Manager.MTPosition):
        print(f"Position Deleted", position.Print())
        MT5Position.objects.filter(position_id=position.Position).delete()
    
    # Clean user position
    def OnPositionClean(self, login):
        print(f"Position Cleaned", login)
        MT5Position.objects.filter(login=login).delete()
