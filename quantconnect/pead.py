# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class PostEarningsDrift(ScreenerAlgorithm):
    """Post-Earnings-Announcement Drift (PEAD) — a free-tier price/volume PROXY.

    True PEAD longs stocks after a positive earnings *surprise* and holds for the
    multi-day drift. Without an earnings feed we proxy the surprise with a strong
    gap-up on a big volume surge (earnings reactions look exactly like this), then
    hold ~3 days. To make it the *real* thing, wire QC's earnings/fundamental data
    (see README) and replace the gap/volume trigger with an actual surprise score.
    """

    window_size = 25
    max_hold_days = 3

    def configure(self):
        self.min_gap = float(self.GetParameter("min_gap") or 0.05)
        self.rvol_min = float(self.GetParameter("rvol_min") or 3.0)

    def signal(self, symbol, sd):
        if sd.window.Count < 21:
            return None
        today, prev = sd.window[0], sd.window[1]
        gap = today.Open / prev.Close - 1.0 if prev.Close > 0 else 0.0
        prior = [sd.window[i] for i in range(1, 21)]
        avg_vol = sum(b.Volume for b in prior) / len(prior)
        rvol = today.Volume / avg_vol if avg_vol > 0 else 0.0
        if not (gap >= self.min_gap and rvol >= self.rvol_min and today.Close > today.Open):
            return None
        atr = sd.atr.Current.Value
        price = self.Securities[symbol].Price
        score = min(1.0, gap / 0.10)
        return (score, price - 2.0 * atr, price + 3.0 * atr)
