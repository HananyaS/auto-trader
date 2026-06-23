"""Momentum baseline: buy recent strength, hold 1-2 days, exit on stop/target/time.

Phase 3 (see ROADMAP.md). One of two baselines; compared against mean-reversion
in backtest. Parameters live in config so they can be swept and validated
out-of-sample (avoid curve-fitting).
"""

from __future__ import annotations

import pandas as pd

from autotrader.strategy.base import SignalSet


class MomentumStrategy:
    name = "momentum"

    def __init__(self, lookback: int = 20, hold_days: int = 2) -> None:
        self.lookback = lookback
        self.hold_days = hold_days

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        """TODO(Phase 3): N-day breakout / positive-momentum entries + exits."""
        raise NotImplementedError("Phase 3: implement momentum signals")
