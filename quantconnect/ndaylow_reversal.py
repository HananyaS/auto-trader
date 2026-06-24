# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class NDayLowReversal(ScreenerAlgorithm):
    """Buy-the-dip: today is the lowest close of the last N days, in an uptrend.

    Long when Close == min(close, last ``lookback`` days) and Close > SMA200
    (pullback within an uptrend). Ranked by dip depth (in ATRs). ATR stop, 2-day
    hold. A simple, well-known short-term reversion.
    """

    window_size = 12

    def configure(self):
        self.lookback = int(self.GetParameter("lookback") or 5)

    def make_indicators(self, symbol):
        return {"sma200": self.SMA(symbol, 200, Resolution.Daily)}  # noqa: F405

    def signal(self, symbol, sd):
        if sd.window.Count < self.lookback + 1:
            return None
        closes = [sd.window[i].Close for i in range(self.lookback)]
        today = sd.window[0]
        price = self.Securities[symbol].Price
        if today.Close > min(closes) or price <= sd.indicators["sma200"].Current.Value:
            return None
        atr = sd.atr.Current.Value
        depth = (sum(closes) / len(closes) - today.Close) / max(atr, 1e-6)
        score = max(0.0, min(1.0, depth / 2.0))
        return (score, price - 1.5 * atr, price + 2.5 * atr)
