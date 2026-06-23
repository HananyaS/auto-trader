"""Tests for indicators and the two signal baselines (Phase 3).

All synthetic data — no network. Verifies entry conditions fire (and don't fire)
where expected, and that exit levels are sane (stop < entry < target).
"""

import numpy as np
import pandas as pd
import pytest

from autotrader.strategy.base import Side
from autotrader.strategy.indicators import prior_rolling_high, rsi
from autotrader.strategy.mean_reversion import MeanReversionStrategy
from autotrader.strategy.momentum import MomentumStrategy


def _frame(close):
    idx = pd.date_range("2024-01-01", periods=len(close))
    close = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000,
        },
        index=idx,
    )


# --- indicators ---------------------------------------------------------------


def test_rsi_bounded_and_high_when_only_gains():
    close = pd.Series(np.arange(1, 31), dtype=float)  # strictly increasing
    r = rsi(close, period=2).dropna()
    assert ((r >= 0) & (r <= 100)).all()
    assert r.iloc[-1] == pytest.approx(100.0)  # no down moves -> RSI 100


def test_rsi_low_after_sharp_drop():
    close = pd.Series([100, 101, 102, 103, 104, 90], dtype=float)  # gains then a plunge
    r = rsi(close, period=2)
    assert r.iloc[-1] < 30  # oversold after the drop


def test_prior_rolling_high_excludes_today():
    s = pd.Series([1, 2, 3, 10, 4], dtype=float)
    ph = prior_rolling_high(s, window=3)
    # at index 3 (value 10), prior 3-day high is max(1,2,3) = 3, so 10 is a breakout
    assert ph.iloc[3] == 3.0
    assert s.iloc[3] > ph.iloc[3]


# --- momentum -----------------------------------------------------------------


def test_momentum_fires_on_breakout():
    # Flat for the lookback window, then a decisive new high.
    close = [100.0] * 25 + [120.0]
    bars = {"AAA": _frame(close)}
    sigs = MomentumStrategy(lookback=20).generate(bars)
    assert "AAA" in sigs
    last = sigs["AAA"][-1]
    assert last.side is Side.BUY
    assert last.stop_loss < 120.0 < last.take_profit
    assert last.max_hold_days == 2


def test_momentum_silent_on_downtrend():
    close = list(np.linspace(120, 80, 40))  # steadily falling -> no new highs
    bars = {"BBB": _frame(close)}
    sigs = MomentumStrategy(lookback=20).generate(bars)
    assert "BBB" not in sigs


# --- mean reversion -----------------------------------------------------------


def test_mean_reversion_fires_when_oversold():
    # Rise, then a sharp multi-day sell-off to drive RSI(2) below the threshold.
    close = [100, 101, 102, 103, 104, 95, 90, 86] + [85.0]
    bars = {"CCC": _frame(close)}
    sigs = MeanReversionStrategy(rsi_period=2, rsi_entry=10.0).generate(bars)
    assert "CCC" in sigs
    entry = sigs["CCC"][0]
    assert entry.side is Side.BUY
    assert entry.stop_loss < entry.take_profit


def test_mean_reversion_silent_on_uptrend():
    close = list(np.linspace(80, 120, 40))  # steady rise -> RSI stays high
    bars = {"DDD": _frame(close)}
    sigs = MeanReversionStrategy(rsi_period=2, rsi_entry=10.0).generate(bars)
    assert "DDD" not in sigs


def test_strategies_are_pure_no_mutation():
    bars = {"EEE": _frame([100.0] * 25 + [130.0])}
    snapshot = bars["EEE"].copy()
    MomentumStrategy().generate(bars)
    MeanReversionStrategy().generate(bars)
    pd.testing.assert_frame_equal(bars["EEE"], snapshot)
