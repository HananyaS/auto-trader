"""Momentum baseline: buy breakouts, hold 1-2 days, exit on stop/target/time.

Phase 3 (see ROADMAP.md). One of two baselines compared in backtest. Long-only.
Entry: today's close makes a new ``lookback``-day high (breakout above the prior
``lookback``-day high). Exits are encoded on each Signal as a stop, a target, and
a max hold of ``hold_days`` (the backtest/live engine enforces them).

Parameters are constructor args so they can be swept and validated out-of-sample
(avoid curve-fitting).
"""

from __future__ import annotations

import pandas as pd

from autotrader.strategy.base import Side, Signal, SignalSet
from autotrader.strategy.indicators import prior_rolling_high


class MomentumStrategy:
    name = "momentum"

    def __init__(
        self,
        lookback: int = 20,
        hold_days: int = 2,
        stop_pct: float = 0.03,
        target_pct: float = 0.05,
    ) -> None:
        self.lookback = lookback
        self.hold_days = hold_days
        self.stop_pct = stop_pct
        self.target_pct = target_pct

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        signals: SignalSet = {}
        for symbol, df in bars.items():
            close = df["close"]
            breakout = close > prior_rolling_high(close, self.lookback)
            entries = [
                _entry_signal(
                    symbol, ts, close.loc[ts], self.hold_days, self.stop_pct, self.target_pct
                )
                for ts, is_entry in breakout.items()
                if bool(is_entry)
            ]
            if entries:
                signals[symbol] = entries
        return signals


def _entry_signal(
    symbol: str,
    ts: pd.Timestamp,
    price: float,
    hold_days: int,
    stop_pct: float,
    target_pct: float,
) -> Signal:
    return Signal(
        symbol=symbol,
        timestamp=ts,
        side=Side.BUY,
        stop_loss=price * (1 - stop_pct),
        take_profit=price * (1 + target_pct),
        max_hold_days=hold_days,
    )
