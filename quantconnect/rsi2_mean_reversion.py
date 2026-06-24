# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class RSI2MeanReversion(ScreenerAlgorithm):
    """Connors RSI(2) mean-reversion with a long-term trend filter.

    Long when a stock in an uptrend (Close > SMA200) becomes very oversold
    (RSI(2) < 10). Exit on a snap back above SMA5, an ATR stop, or after 2 days.
    Evidence: beat our random-entry null out-of-sample.
    """

    def configure(self):
        self.rsi_entry = float(self.GetParameter("rsi_entry") or 10.0)
        self.max_hold_days = int(self.GetParameter("max_hold") or 2)

    def make_indicators(self, symbol):
        return {
            "rsi2": self.RSI(symbol, 2, MovingAverageType.Wilders, Resolution.Daily),  # noqa: F405
            "sma5": self.SMA(symbol, 5, Resolution.Daily),  # noqa: F405
            "sma200": self.SMA(symbol, 200, Resolution.Daily),  # noqa: F405
        }

    def signal(self, symbol, sd):
        price = self.Securities[symbol].Price
        rsi2 = sd.indicators["rsi2"].Current.Value
        sma200 = sd.indicators["sma200"].Current.Value
        if price <= sma200 or rsi2 >= self.rsi_entry:
            return None
        atr = sd.atr.Current.Value
        score = max(0.0, (self.rsi_entry - rsi2) / self.rsi_entry)  # deeper oversold = stronger
        stop = price - 1.5 * atr
        target = max(sd.indicators["sma5"].Current.Value, price + 2.5 * atr)
        return (score, stop, target)
