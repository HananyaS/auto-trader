"""Technical indicators as pure functions over price Series.

Kept dependency-light (pandas only) and side-effect free so they behave
identically in backtest and live, and are trivial to unit-test.
"""

from __future__ import annotations

import pandas as pd


def rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's Relative Strength Index in [0, 100].

    Uses Wilder smoothing (EWMA with alpha = 1/period). A zero average loss
    yields RSI = 100 (no down moves over the window).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - 100 / (1 + rs)
    # avg_loss == 0 -> rs == inf -> RSI 100; both zero (flat) -> treat as neutral 50.
    out = out.where(avg_loss != 0, 100.0)
    out = out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0)
    return out


def prior_rolling_high(series: pd.Series, window: int) -> pd.Series:
    """Highest value over the ``window`` bars *ending yesterday* (excludes today).

    Useful for breakout entries: ``today > prior_rolling_high`` means a new high.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    return series.shift(1).rolling(window).max()
