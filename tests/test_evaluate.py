"""Tests for the validation harness: new metrics, exposure/per-trade, null, walk-forward."""

import numpy as np
import pandas as pd

from autotrader.backtest.evaluate import (
    RandomEntryStrategy,
    dominant_regime,
    random_entry_benchmark,
    regime_label,
    single_pattern_strategy,
    walk_forward,
)
from autotrader.backtest.metrics import (
    bootstrap_ci,
    expectancy,
    percentile_rank,
    profit_factor,
    t_stat,
)
from autotrader.backtest.runner import run_backtest
from autotrader.strategy.momentum import MomentumStrategy
from autotrader.strategy.screener import default_patterns


def _frame(close, *, high=None, low=None, volume=1_000_000):
    idx = pd.date_range("2020-01-01", periods=len(close), freq="B")
    c = pd.Series(close, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": c,
            "high": pd.Series(high, index=idx, dtype=float) if high is not None else c * 1.01,
            "low": pd.Series(low, index=idx, dtype=float) if low is not None else c * 0.99,
            "close": c,
            "volume": volume,
        }
    )


# --- pure metrics -------------------------------------------------------------


def test_expectancy_and_profit_factor():
    r = [0.02, -0.01, 0.03, -0.01]
    assert expectancy(r) == 0.0075
    assert profit_factor(r) == (0.05 / 0.02)  # wins .05, losses .02
    assert profit_factor([0.01, 0.02]) == float("inf")  # no losses


def test_t_stat_sign_and_magnitude():
    assert t_stat([0.01] * 10) == 0.0  # zero variance -> undefined -> 0
    pos = t_stat([0.02, 0.03, 0.01, 0.025, 0.015])
    assert pos > 0
    assert t_stat([-x for x in [0.02, 0.03, 0.01, 0.025, 0.015]]) < 0


def test_bootstrap_ci_is_seeded_and_brackets_mean():
    data = list(np.random.default_rng(1).normal(0.01, 0.02, 200))
    lo1, hi1 = bootstrap_ci(data, seed=42)
    lo2, hi2 = bootstrap_ci(data, seed=42)
    assert (lo1, hi1) == (lo2, hi2)  # deterministic
    assert lo1 < np.mean(data) < hi1


def test_percentile_rank():
    dist = list(range(100))
    assert percentile_rank(50, dist) == 0.50
    assert percentile_rank(200, dist) == 1.0
    assert percentile_rank(-5, dist) == 0.0


# --- runner: exposure + per-trade returns -------------------------------------


def test_backtest_reports_exposure_and_trade_returns():
    close = [100.0] * 25 + list(102 + 2 * np.arange(30, dtype=float))
    res = run_backtest({"UP": _frame(close)}, MomentumStrategy(lookback=20), starting_cash=10_000)
    assert 0.0 <= res.exposure <= 1.0
    assert res.num_trades == len(res.trade_returns)
    if res.num_trades:
        assert np.isfinite(res.expectancy)
        assert res.return_on_exposure != 0.0


# --- random-entry null --------------------------------------------------------


def test_random_entry_strategy_is_seeded_and_bounded():
    bars = {s: _frame(list(100 + np.arange(80, dtype=float))) for s in ("A", "B", "C")}
    a = RandomEntryStrategy(10, seed=7).generate(bars)
    b = RandomEntryStrategy(10, seed=7).generate(bars)
    assert {k: [s.timestamp for s in v] for k, v in a.items()} == {
        k: [s.timestamp for s in v] for k, v in b.items()
    }  # deterministic
    assert sum(len(v) for v in a.values()) <= 10


def test_random_entry_benchmark_returns_distribution():
    bars = {s: _frame(list(100 + np.arange(80, dtype=float))) for s in ("A", "B", "C")}
    null = random_entry_benchmark(bars, n_trades=5, n_runs=8, seed=0)
    assert len(null) == 8
    assert all(np.isfinite(r.total_return) for r in null)


# --- walk-forward -------------------------------------------------------------


def test_walk_forward_folds_are_ordered_and_nonoverlapping():
    bars = {"X": _frame(list(100 + np.arange(300, dtype=float)))}
    folds = walk_forward(bars, lambda _t: MomentumStrategy(lookback=20), n_splits=3)
    assert 1 <= len(folds) <= 3
    for (s, e, _r) in folds:
        assert s <= e
    for (_s0, e0, _), (s1, _e1, _) in zip(folds, folds[1:], strict=False):
        assert e0 <= s1  # contiguous, non-overlapping in order


# --- regime -------------------------------------------------------------------


def test_regime_label_and_dominant():
    up = pd.Series(np.linspace(100, 300, 260), index=pd.date_range("2020-01-01", periods=260))
    labels = regime_label(up)
    assert labels.dropna().iloc[-1] == "bull"
    assert dominant_regime(up, up.index[210], up.index[-1]) == "bull"


# --- per-pattern attribution --------------------------------------------------


def test_single_pattern_strategies_are_backtestable():
    # Construct a breakout frame that fires the volume/52wk patterns; just assert
    # every pattern wrapper yields a finite BacktestResult without error.
    base = [100.0] * 255
    df = _frame(
        base + [110.0],
        high=[100.2] * 255 + [110.5],
        low=[99.8] * 256,
        volume=[200_000] * 255 + [2_000_000],
    )
    for pat in default_patterns():
        strat = single_pattern_strategy(pat)
        res = run_backtest({"AAA": df}, strat, starting_cash=10_000)
        assert np.isfinite(res.total_return)
        assert res.num_trades >= 0
