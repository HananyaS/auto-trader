"""Tests for Phase 4 backtesting: pure metrics + the backtrader runner.

Synthetic data only — no network. The runner tests assert structural sanity
(trades happen where expected, metrics are finite), not specific P&L.
"""

import numpy as np
import pandas as pd
import pytest

from autotrader.backtest.metrics import (
    annualized_sharpe,
    annualized_sortino,
    buy_and_hold_return,
    train_test_split,
)
from autotrader.backtest.runner import run_backtest
from autotrader.strategy.momentum import MomentumStrategy


def _frame(close):
    idx = pd.date_range("2024-01-01", periods=len(close))
    close = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.02,
            "low": close * 0.98,
            "close": close,
            "volume": 10_000,
        },
        index=idx,
    )


# --- pure metrics -------------------------------------------------------------


def test_sharpe_zero_when_no_variance():
    assert annualized_sharpe(pd.Series([0.01, 0.01, 0.01])) == 0.0


def test_sharpe_positive_for_steady_gains():
    r = pd.Series([0.01, 0.012, 0.009, 0.011, 0.013])
    assert annualized_sharpe(r) > 0


def test_sortino_ignores_upside_volatility():
    r = pd.Series([0.02, -0.01, 0.03, -0.005, 0.04])
    s = annualized_sortino(r)
    assert np.isfinite(s) and s != 0.0


def test_buy_and_hold_return():
    assert buy_and_hold_return(pd.Series([100.0, 110.0])) == pytest.approx(0.10)


def test_train_test_split_partitions_by_date():
    bars = {"X": _frame(list(range(100, 140)))}
    train, test = train_test_split(bars, "2024-01-21")
    assert train["X"].index.max() < pd.Timestamp("2024-01-21")
    assert test["X"].index.min() >= pd.Timestamp("2024-01-21")


# --- runner -------------------------------------------------------------------


def test_run_backtest_executes_trades_in_uptrend():
    close = [100.0] * 25 + list(102 + 2 * np.arange(30, dtype=float))  # flat then strong rise
    bars = {"UP": _frame(close)}
    result = run_backtest(bars, MomentumStrategy(lookback=20), starting_cash=10_000)

    assert result.num_trades >= 1
    assert result.final_value > 0
    assert np.isfinite(result.total_return)
    assert np.isfinite(result.sharpe)
    assert 0.0 <= result.win_rate <= 1.0


def test_run_backtest_no_trades_in_downtrend():
    close = list(np.linspace(160, 80, 50))  # steadily falling -> no breakouts
    bars = {"DOWN": _frame(close)}
    result = run_backtest(bars, MomentumStrategy(lookback=20), starting_cash=10_000)

    assert result.num_trades == 0
    assert result.total_return == 0.0  # untouched capital


def test_run_backtest_skips_empty_feeds():
    # A single empty feed otherwise makes backtrader's next() never fire, silently
    # halting the whole run (real-world cause: a ticker with no bars in the window).
    close = [100.0] * 25 + list(102 + 2 * np.arange(30, dtype=float))
    bars = {
        "UP": _frame(close),
        "EMPTY": _frame(close).iloc[0:0],  # zero rows
    }
    result = run_backtest(bars, MomentumStrategy(lookback=20), starting_cash=10_000)
    assert result.num_trades >= 1  # the good feed still trades


def test_run_backtest_raises_when_all_feeds_unusable():
    bars = {"A": _frame([100.0] * 25).iloc[0:0], "B": _frame([100.0]).iloc[0:0]}
    with pytest.raises(ValueError, match="no usable data feeds"):
        run_backtest(bars, MomentumStrategy(), starting_cash=10_000)
