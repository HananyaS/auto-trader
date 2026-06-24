# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class CrossSectionalMomentum(ScreenerAlgorithm):
    """Daily cross-sectional short-term momentum.

    Scores every liquid name by its trailing ``lookback``-day return; the base
    spine then longs the top ``max_positions`` by score and holds 2 days. A clean
    QC universe-ranking pattern that's hard to do well on messy data.
    """

    window_size = 10

    def configure(self):
        self.lookback = int(self.GetParameter("lookback") or 5)

    def signal(self, symbol, sd):
        if sd.window.Count < self.lookback + 1:
            return None
        today, past = sd.window[0], sd.window[self.lookback]
        ret = today.Close / past.Close - 1.0 if past.Close > 0 else 0.0
        if ret <= 0:
            return None  # long-only: winners only
        atr = sd.atr.Current.Value
        price = self.Securities[symbol].Price
        score = min(1.0, ret / 0.10)  # +10% over the lookback -> full conviction
        return (score, price - 1.5 * atr, price + 2.5 * atr)
