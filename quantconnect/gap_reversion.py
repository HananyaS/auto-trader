# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class GapReversion(ScreenerAlgorithm):
    """Long the recovery of an overnight gap-DOWN back toward the prior close.

    Long when today gaps down >=2% (Open <= prevClose*0.98) but closes green and
    still below the prior close (Close > Open, Close < prevClose) — fading the gap
    toward its fill. Target = prior close; ATR stop below the low; 1-day hold.
    Evidence: gap-fill beat our random-entry null out-of-sample.
    """

    max_hold_days = 1

    def configure(self):
        self.min_gap = float(self.GetParameter("min_gap") or 0.02)

    def signal(self, symbol, sd):
        if sd.window.Count < 2:
            return None
        today, prev = sd.window[0], sd.window[1]
        prev_close = prev.Close
        gap = today.Open / prev_close - 1.0 if prev_close > 0 else 0.0
        if not (gap <= -self.min_gap and today.Close > today.Open and today.Close < prev_close):
            return None
        atr = sd.atr.Current.Value
        price = self.Securities[symbol].Price
        target = prev_close
        if target <= price:
            return None
        score = max(0.0, min(1.0, (-gap) / 0.05))
        return (score, today.Low - 0.25 * atr, target)
