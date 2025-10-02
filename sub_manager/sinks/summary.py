import MT5Manager
from trading.models import MT5Summary

def save_mt5_summary(summary_obj:MT5Manager.MTSummary):
    summary, _ = MT5Summary.objects.update_or_create(
        symbol=summary_obj.Symbol,
        defaults=dict(
            digits=getattr(summary_obj, "Digits", 0),
            position_clients=getattr(summary_obj, "PositionClients", 0),
            position_coverage=getattr(summary_obj, "PositionCoverage", 0),

            volume_buy_clients=getattr(summary_obj, "VolumeBuyClients", 0),
            volume_buy_clients_ext=getattr(summary_obj, "VolumeBuyClientsExt", 0),
            volume_buy_coverage=getattr(summary_obj, "VolumeBuyCoverage", 0),
            volume_buy_coverage_ext=getattr(summary_obj, "VolumeBuyCoverageExt", 0),

            volume_sell_clients=getattr(summary_obj, "VolumeSellClients", 0),
            volume_sell_clients_ext=getattr(summary_obj, "VolumeSellClientsExt", 0),
            volume_sell_coverage=getattr(summary_obj, "VolumeSellCoverage", 0),
            volume_sell_coverage_ext=getattr(summary_obj, "VolumeSellCoverageExt", 0),

            volume_net=getattr(summary_obj, "VolumeNet", 0),

            price_buy_clients=getattr(summary_obj, "PriceBuyClients", 0),
            price_buy_coverage=getattr(summary_obj, "PriceBuyCoverage", 0),
            price_sell_clients=getattr(summary_obj, "PriceSellClients", 0),
            price_sell_coverage=getattr(summary_obj, "PriceSellCoverage", 0),

            profit_clients=getattr(summary_obj, "ProfitClients", 0),
            profit_coverage=getattr(summary_obj, "ProfitCoverage", 0),
            profit_full_clients=getattr(summary_obj, "ProfitFullClients", 0),
            profit_full_coverage=getattr(summary_obj, "ProfitFullCoverage", 0),
            profit_uncovered=getattr(summary_obj, "ProfitUncovered", 0),
            profit_uncovered_full=getattr(summary_obj, "ProfitUncoveredFull", 0),
        )
    )
    return summary


class SummarySink:
    def OnSummaryUpdate(self, summary:MT5Manager.MTSummary):
        print("Summary received")
        save_mt5_summary(summary)