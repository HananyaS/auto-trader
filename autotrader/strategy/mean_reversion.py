"""Mean-reversion baseline: buy oversold dips, expect a 1-2 day bounce.

Phase 3 (see ROADMAP.md). One of two baselines compared in backtest. Long-only.
Entry: short-period RSI drops below ``rsi_entry`` (oversold). Exits are encoded on
each Signal as a stop, a target, and a max hold of ``hold_days`` (the
backtest/live engine enforces them).

Parameters are constructor args so they can be swept and validated out-of-sample
(avoid curve-fitting).
"""

from __future__ import annotations

import pandas as pd

from autotrader.strategy.base import Side, Signal, SignalSet
from autotrader.strategy.indicators import rsi


class MeanReversionStrategy:
    name = "mean_reversion"

    def __init__(
        self,
        rsi_period: int = 2,
        rsi_entry: float = 10.0,
        hold_days: int = 2,
        stop_pct: float = 0.03,
        target_pct: float = 0.05,
    ) -> None:
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.hold_days = hold_days
        self.stop_pct = stop_pct
        self.target_pct = target_pct

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        signals: SignalSet = {}
        for symbol, df in bars.items():
            close = df["close"]
            oversold = rsi(close, self.rsi_period) < self.rsi_entry
            entries = [
                Signal(
                    symbol=symbol,
                    timestamp=ts,
                    side=Side.BUY,
                    stop_loss=close.loc[ts] * (1 - self.stop_pct),
                    take_profit=close.loc[ts] * (1 + self.target_pct),
                    max_hold_days=self.hold_days,
                )
                for ts, is_entry in oversold.items()
                if bool(is_entry)
            ]
            if entries:
                signals[symbol] = entries
        return signals
