"""Common signal types and the Strategy protocol.

A Strategy is a pure function of bars -> signals, so backtest and live share
one implementation. Exit handling for the 1-2 day horizon (time-based exit +
stop-loss + take-profit) lives alongside entries in the signal output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import pandas as pd


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"
    FLAT = "flat"


@dataclass(frozen=True)
class Signal:
    """A single dated entry/exit intent for one symbol."""

    symbol: str
    timestamp: pd.Timestamp
    side: Side
    # Optional exit guidance for the 1-2 day hold; sizing comes from the risk layer.
    stop_loss: float | None = None
    take_profit: float | None = None
    max_hold_days: int = 2


# {symbol: [Signal, ...]} produced for a backtest window or a single live bar.
SignalSet = dict[str, list[Signal]]


class Strategy(Protocol):
    """Pure signal generator. Implementations: momentum, mean_reversion."""

    name: str

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        """Map {symbol: OHLCV} -> signals. Must be side-effect free."""
        ...
