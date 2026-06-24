# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class Week52Breakout(ScreenerAlgorithm):
    """52-week-high breakout with a relative-volume filter.

    Long when price prints a new ~252-day high on RVOL >= 1.5 (no overhead
    resistance + real participation). ATR stop/target, 1-2 day hold.
    Note: this *failed* our biased local test (survivorship/selection); included
    here to re-test on QC's clean data — judge it on the hold-out, not faith.
    """

    window_size = 25

    def configure(self):
        self.rvol_min = float(self.GetParameter("rvol_min") or 1.5)

    def make_indicators(self, symbol):
        # 252-day high of daily highs (updates end-of-day; today's pre-close price
        # breaking above it = a new high vs prior history).
        return {"hi252": self.MAX(symbol, 252, Resolution.Daily, Field.High)}  # noqa: F405

    def signal(self, symbol, sd):
        if sd.window.Count < 21:
            return None
        today = sd.window[0]
        prior = [sd.window[i] for i in range(1, 21)]
        avg_vol = sum(b.Volume for b in prior) / len(prior)
        rvol = today.Volume / avg_vol if avg_vol > 0 else 0.0
        price = self.Securities[symbol].Price
        hi = sd.indicators["hi252"].Current.Value
        if not (price > hi and rvol >= self.rvol_min):
            return None
        atr = sd.atr.Current.Value
        score = 0.5 * min(1.0, (rvol - self.rvol_min) / 2.0) + 0.5 * min(1.0, (price - hi) / max(atr, 1e-6))
        return (score, price - 1.5 * atr, price + 2.5 * atr)
