# region imports
from AlgorithmImports import *  # noqa: F403
from base_screener import ScreenerAlgorithm
# endregion


class CombinedScreener(ScreenerAlgorithm):
    """Ensemble screener: composite of several daily reversion/volume patterns.

    Mirrors this repo's ``ScreenerStrategy`` on QC. Each enabled pattern emits a
    raw score in [0, 1]; the composite is a weight-normalized mean with a
    confluence bonus (more patterns agreeing -> higher score). The base spine then
    longs the top names by composite score with ATR stop/target and a 2-day hold.

    Deliberately ensembles the *correlated* mean-reversion + volume cluster (the
    patterns that beat our random-entry null) and NOT the long-breakout patterns:
    breakouts fire in the opposite regime, so blending them dilutes the edge (which
    is exactly what hurt the naive all-patterns composite in our local tests).
    """

    window_size = 25

    weights = {
        "volspike": 1.2,
        "bollinger": 1.0,
        "rsi2": 0.9,
        "ibs": 0.9,
        "gap": 0.8,
        "ndaylow": 0.7,
    }

    def configure(self):
        self.min_score = float(self.GetParameter("min_score") or 0.40)
        self.confluence_bonus = float(self.GetParameter("confluence_bonus") or 0.15)

    def make_indicators(self, symbol):
        return {
            "rsi2": self.RSI(symbol, 2, MovingAverageType.Wilders, Resolution.Daily),  # noqa: F405
            "sma5": self.SMA(symbol, 5, Resolution.Daily),  # noqa: F405
            "sma200": self.SMA(symbol, 200, Resolution.Daily),  # noqa: F405
            "bb": self.BB(symbol, 20, 2, MovingAverageType.Simple, Resolution.Daily),  # noqa: F405
        }

    def signal(self, symbol, sd):
        price = self.Securities[symbol].Price
        atr = sd.atr.Current.Value
        if atr <= 0:
            return None

        raws = {}
        for name in self.weights:
            r = getattr(self, "_" + name)(symbol, sd, price)
            if r and r > 0:
                raws[name] = min(1.0, r)
        if not raws:
            return None

        w_total = sum(self.weights[n] for n in raws)
        base = sum(self.weights[n] * raws[n] for n in raws) / w_total
        score = min(1.0, base * (1.0 + self.confluence_bonus * (len(raws) - 1)))
        if score < self.min_score:
            return None
        return (score, price - 1.5 * atr, price + 2.5 * atr)

    # --- per-pattern raw scores (mirror the standalone algos) ---------------

    def _rsi2(self, symbol, sd, price):
        rsi2 = sd.indicators["rsi2"].Current.Value
        if rsi2 >= 10 or price <= sd.indicators["sma200"].Current.Value:
            return 0.0
        return (10.0 - rsi2) / 10.0

    def _bollinger(self, symbol, sd, price):
        bb = sd.indicators["bb"]
        lower, mid, upper = (
            bb.LowerBand.Current.Value, bb.MiddleBand.Current.Value, bb.UpperBand.Current.Value
        )
        bar = sd.window[0]
        if bar.Low >= lower or price <= lower or price <= sd.indicators["sma200"].Current.Value:
            return 0.0
        if mid <= price:
            return 0.0
        return (mid - price) / max(upper - lower, 1e-6) * 2.0

    def _volspike(self, symbol, sd, price):
        if sd.window.Count < 21:
            return 0.0
        today = sd.window[0]
        prior = [sd.window[i] for i in range(1, 21)]
        prior_high = max(b.High for b in prior)
        avg_vol = sum(b.Volume for b in prior) / len(prior)
        rvol = today.Volume / avg_vol if avg_vol > 0 else 0.0
        if not (price > prior_high and rvol >= 2.0 and today.Close > today.Open):
            return 0.0
        return (rvol - 2.0) / 3.0

    def _ibs(self, symbol, sd, price):
        bar = sd.window[0]
        rng = bar.High - bar.Low
        if rng <= 0 or price <= sd.indicators["sma200"].Current.Value:
            return 0.0
        ibs = (bar.Close - bar.Low) / rng
        return (0.2 - ibs) / 0.2 if ibs < 0.2 else 0.0

    def _gap(self, symbol, sd, price):
        if sd.window.Count < 2:
            return 0.0
        today, prev = sd.window[0], sd.window[1]
        if prev.Close <= 0:
            return 0.0
        gap = today.Open / prev.Close - 1.0
        if not (gap <= -0.02 and today.Close > today.Open and today.Close < prev.Close):
            return 0.0
        return (-gap) / 0.05

    def _ndaylow(self, symbol, sd, price):
        if sd.window.Count < 6:
            return 0.0
        closes = [sd.window[i].Close for i in range(5)]
        today = sd.window[0]
        if today.Close > min(closes) or price <= sd.indicators["sma200"].Current.Value:
            return 0.0
        depth = (sum(closes) / len(closes) - today.Close) / max(sd.atr.Current.Value, 1e-6)
        return min(1.0, depth / 2.0)
