# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class BollingerReversion(ScreenerAlgorithm):
    """Bollinger-band reversion in an uptrend.

    Long when price pokes below the lower band intrabar but closes back inside it
    (Low < lower, Close > lower), with Close > SMA200. Target the mid band; ATR
    stop below the low; 2-day max hold.
    Evidence: beat our random-entry null out-of-sample.
    """

    def configure(self):
        self.bb_period = int(self.GetParameter("bb_period") or 20)
        self.num_std = float(self.GetParameter("num_std") or 2.0)

    def make_indicators(self, symbol):
        return {
            "bb": self.BB(symbol, self.bb_period, self.num_std, MovingAverageType.Simple, Resolution.Daily),  # noqa: F405, E501
            "sma200": self.SMA(symbol, 200, Resolution.Daily),  # noqa: F405
        }

    def signal(self, symbol, sd):
        bar = sd.window[0]  # most recent daily bar
        price = self.Securities[symbol].Price
        bb = sd.indicators["bb"]
        lower, mid, upper = bb.LowerBand.Current.Value, bb.MiddleBand.Current.Value, bb.UpperBand.Current.Value
        if bar.Low >= lower or price <= lower or price <= sd.indicators["sma200"].Current.Value:
            return None
        if mid <= price:
            return None  # need room back up to the mean
        atr = sd.atr.Current.Value
        score = max(0.0, min(1.0, (mid - price) / max(upper - lower, 1e-6) * 2.0))
        return (score, bar.Low - 0.25 * atr, mid)
