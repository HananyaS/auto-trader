# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class IBSMeanReversion(ScreenerAlgorithm):
    """Internal Bar Strength (IBS) mean-reversion in an uptrend.

    IBS = (Close - Low) / (High - Low): low IBS means the bar closed near its low
    (weak close → likely bounce). Long when IBS < 0.2 and Close > SMA200; exit on
    a snap back above SMA5, an ATR stop, or after 2 days. A classic, robust
    daily-bar reversion edge.
    """

    def configure(self):
        self.ibs_entry = float(self.GetParameter("ibs_entry") or 0.2)

    def make_indicators(self, symbol):
        return {
            "sma5": self.SMA(symbol, 5, Resolution.Daily),  # noqa: F405
            "sma200": self.SMA(symbol, 200, Resolution.Daily),  # noqa: F405
        }

    def signal(self, symbol, sd):
        bar = sd.window[0]
        rng = bar.High - bar.Low
        if rng <= 0:
            return None
        ibs = (bar.Close - bar.Low) / rng
        price = self.Securities[symbol].Price
        if ibs >= self.ibs_entry or price <= sd.indicators["sma200"].Current.Value:
            return None
        atr = sd.atr.Current.Value
        score = max(0.0, (self.ibs_entry - ibs) / self.ibs_entry)
        target = max(sd.indicators["sma5"].Current.Value, price + 2.0 * atr)
        return (score, price - 1.5 * atr, target)
