"""Strategy validation harness (see plan).

Goes beyond a single backtest to answer two questions honestly:
- **Edge?** ``random_entry_benchmark`` builds a Monte-Carlo null of random entries
  matched on trade count + holding, so we can rank a strategy's result against luck.
- **Robust?** ``walk_forward`` evaluates over rolling out-of-sample windows, and
  ``dominant_regime`` tags each window bull/bear (SPY 200-DMA).
Plus ``single_pattern_strategy`` makes each screener pattern independently backtestable.

Everything reuses ``run_backtest`` so costs/sizing/exits match the live path.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from autotrader.backtest.runner import BacktestResult, run_backtest
from autotrader.strategy.base import Side, Signal, Strategy
from autotrader.strategy.indicators import atr, sma
from autotrader.strategy.screener import PatternFn, ScreenerStrategy

Bars = dict[str, pd.DataFrame]


# --- random-entry null (edge test) -------------------------------------------


class RandomEntryStrategy:
    """Emits a fixed number of random BUY signals with ATR stop/target.

    The null hypothesis: entry *selection* adds nothing. A real strategy should
    beat the distribution of these random runs.
    """

    name = "random_entry"

    def __init__(
        self,
        n_trades: int,
        *,
        hold_days: int = 2,
        atr_period: int = 14,
        stop_mult: float = 1.5,
        target_mult: float = 2.5,
        seed: int = 0,
        min_history: int = 30,
    ) -> None:
        self.n_trades = n_trades
        self.hold_days = hold_days
        self.atr_period = atr_period
        self.stop_mult = stop_mult
        self.target_mult = target_mult
        self.seed = seed
        self.min_history = min_history

    def generate(self, bars: Bars):
        rng = np.random.default_rng(self.seed)
        pool: list[tuple[str, pd.Timestamp, float, float]] = []
        for sym, df in bars.items():
            if len(df) < self.min_history + self.hold_days:
                continue
            a = atr(df, self.atr_period)
            usable = df.index[self.min_history : len(df) - self.hold_days]
            for ts in usable:
                av = a.loc[ts]
                if np.isfinite(av) and av > 0:
                    pool.append((sym, ts, float(df["close"].loc[ts]), float(av)))
        if not pool:
            return {}
        k = min(self.n_trades, len(pool))
        out: dict[str, list[Signal]] = {}
        for i in rng.choice(len(pool), size=k, replace=False):
            sym, ts, price, av = pool[i]
            out.setdefault(sym, []).append(
                Signal(
                    sym,
                    ts,
                    Side.BUY,
                    stop_loss=price - self.stop_mult * av,
                    take_profit=price + self.target_mult * av,
                    max_hold_days=self.hold_days,
                )
            )
        return out


def random_entry_benchmark(
    bars: Bars,
    *,
    n_trades: int,
    hold_days: int = 2,
    n_runs: int = 200,
    seed: int = 0,
    **bt_kwargs,
) -> list[BacktestResult]:
    """Run ``n_runs`` random-entry backtests -> the null distribution of results."""
    results = []
    for run in range(n_runs):
        strat = RandomEntryStrategy(n_trades, hold_days=hold_days, seed=seed + run)
        try:
            results.append(run_backtest(bars, strat, **bt_kwargs))
        except ValueError:
            continue
    return results


# --- per-pattern attribution --------------------------------------------------


def single_pattern_strategy(pattern: PatternFn, *, min_score: float = 0.01) -> ScreenerStrategy:
    """A screener restricted to ONE pattern, so it can be backtested standalone."""
    return ScreenerStrategy(
        patterns=[pattern], weights={pattern.name: 1.0}, min_score=min_score
    )


# --- walk-forward (robust OOS) ------------------------------------------------


def _all_dates(bars: Bars) -> pd.DatetimeIndex:
    idx: set = set()
    for df in bars.values():
        idx |= set(df.index)
    return pd.DatetimeIndex(sorted(idx))


def slice_bars(bars: Bars, start: pd.Timestamp, end: pd.Timestamp) -> Bars:
    out = {s: df.loc[start:end] for s, df in bars.items()}
    return {s: df for s, df in out.items() if not df.empty}


def walk_forward(
    bars: Bars,
    strategy_factory: Callable[[Bars], Strategy],
    *,
    n_splits: int = 4,
    min_train_frac: float = 0.4,
    **bt_kwargs,
) -> list[tuple[pd.Timestamp, pd.Timestamp, BacktestResult]]:
    """Evaluate over ``n_splits`` contiguous OOS windows after an initial train span.

    ``strategy_factory(train_bars) -> Strategy`` ignores train for fixed strategies,
    but the signature is ready for future parameter tuning. Returns
    (test_start, test_end, result) per fold.
    """
    dates = _all_dates(bars)
    n = len(dates)
    if n < 10:
        return []
    bounds = np.linspace(int(n * min_train_frac), n, n_splits + 1).astype(int)
    folds = []
    for k in range(n_splits):
        t0, t1 = bounds[k], bounds[k + 1]
        if t1 - t0 < 5:
            continue
        train = slice_bars(bars, dates[0], dates[t0 - 1])
        test = slice_bars(bars, dates[t0], dates[t1 - 1])
        if not test:
            continue
        try:
            result = run_backtest(test, strategy_factory(train), **bt_kwargs)
        except ValueError:
            continue
        folds.append((dates[t0], dates[t1 - 1], result))
    return folds


# --- regime (bull/bear) -------------------------------------------------------


def regime_label(spy_close: pd.Series, period: int = 200) -> pd.Series:
    """'bull' where SPY closes above its ``period``-day SMA, else 'bear'."""
    trend = sma(spy_close, period)
    return pd.Series(np.where(spy_close > trend, "bull", "bear"), index=spy_close.index)


def dominant_regime(spy_close: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Majority regime over [start, end]; 'unknown' if no SPY coverage."""
    labels = regime_label(spy_close).loc[start:end]
    if labels.empty:
        return "unknown"
    return "bull" if (labels == "bull").mean() >= 0.5 else "bear"


def mean_metric(results: list[BacktestResult], attr: str) -> float:
    """Mean of a metric across results (e.g. aggregate walk-forward total_return)."""
    vals = [getattr(r, attr) for r in results]
    return float(np.mean(vals)) if vals else 0.0
