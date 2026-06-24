# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class VolumeSpikeBreakout(ScreenerAlgorithm):
    """Volume-confirmed breakout (highest local Sharpe + edge in our tests).

    Long when price closes above its prior 20-day high on a relative-volume spike
    (RVOL >= 2) and an up day. ATR stop/target, 1-2 day hold.
    Evidence: best Sharpe and ~92nd percentile vs the random null in our backtest.
    """

    window_size = 25  # need 20-day high + a volume baseline

    def configure(self):
        self.rvol_min = float(self.GetParameter("rvol_min") or 2.0)
        self.lookback = int(self.GetParameter("lookback") or 20)

    def signal(self, symbol, sd):
        if sd.window.Count < self.lookback + 1:
            return None
        bars = [sd.window[i] for i in range(self.lookback + 1)]
        today = bars[0]
        prior = bars[1:]                       # the 20 bars before today
        prior_high = max(b.High for b in prior)
        avg_vol = sum(b.Volume for b in prior) / len(prior)
        rvol = today.Volume / avg_vol if avg_vol > 0 else 0.0

        price = self.Securities[symbol].Price
        if not (price > prior_high and rvol >= self.rvol_min and today.Close > today.Open):
            return None
        atr = sd.atr.Current.Value
        score = max(0.0, min(1.0, (rvol - self.rvol_min) / 3.0))
        return (score, price - 1.5 * atr, price + 2.0 * atr)
