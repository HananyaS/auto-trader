# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class DonchianBreakout(ScreenerAlgorithm):
    """Donchian channel breakout (turtle-style), short-term variant.

    Long when price breaks above the prior ``lookback``-day high (no volume
    filter — the pure price breakout). Ranked by breakout distance in ATRs; wider
    ATR stop/target; 2-day hold. A momentum baseline for the search batch.
    """

    def configure(self):
        self.lookback = int(self.GetParameter("lookback") or 20)

    def make_indicators(self, symbol):
        return {"hi": self.MAX(symbol, self.lookback, Resolution.Daily, Field.High)}  # noqa: F405

    def signal(self, symbol, sd):
        price = self.Securities[symbol].Price
        hi = sd.indicators["hi"].Current.Value
        if price <= hi:
            return None
        atr = sd.atr.Current.Value
        score = min(1.0, (price - hi) / max(atr, 1e-6))
        return (score, price - 2.0 * atr, price + 3.0 * atr)
