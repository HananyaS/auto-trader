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


def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return series.rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (span = period)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    """Wilder's True Range = max(H-L, |H-prevC|, |L-prevC|), row-wise."""
    prev_close = df["close"].shift(1)
    hl = df["high"] - df["low"]
    hc = (df["high"] - prev_close).abs()
    lc = (df["low"] - prev_close).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder smoothing of true range)."""
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()


def bollinger(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands -> (lower, mid, upper). ``mid`` is the SMA; bands are ±num_std·σ."""
    if period < 1:
        raise ValueError("period must be >= 1")
    mid = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    return mid - num_std * std, mid, mid + num_std * std


def rvol(volume: pd.Series, period: int = 20) -> pd.Series:
    """Relative volume = today's volume / average of the *prior* ``period`` bars.

    Uses ``shift(1)`` so today's own volume is excluded from the baseline
    (avoids look-ahead/self-reference).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    baseline = volume.rolling(period).mean().shift(1)
    return volume / baseline


def adr_pct(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Average Daily Range as a percent: mean(high/low - 1) over ``period``, ×100."""
    if period < 1:
        raise ValueError("period must be >= 1")
    return ((df["high"] / df["low"] - 1.0).rolling(period).mean()) * 100.0


def gap_pct(df: pd.DataFrame) -> pd.Series:
    """Overnight gap as a fraction: today's open / prior close - 1."""
    return df["open"] / df["close"].shift(1) - 1.0
