"""Mean-reversion baseline: buy short-term oversold dips, expect a 1-2 day bounce.

Phase 3 (see ROADMAP.md). One of two baselines; compared against momentum in
backtest. Parameters live in config so they can be swept and validated
out-of-sample (avoid curve-fitting).
"""

from __future__ import annotations

import pandas as pd

from autotrader.strategy.base import SignalSet


class MeanReversionStrategy:
    name = "mean_reversion"

    def __init__(self, rsi_period: int = 2, rsi_entry: float = 10.0, hold_days: int = 2) -> None:
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.hold_days = hold_days

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        """TODO(Phase 3): oversold (e.g. low RSI / below-MA) entries + exits."""
        raise NotImplementedError("Phase 3: implement mean-reversion signals")
