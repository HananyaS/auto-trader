"""Performance metrics + helpers — pure functions, no backtrader dependency.

Separated from the runner so the math is unit-testable in isolation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def annualized_sharpe(daily_returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized Sharpe ratio (risk-free assumed ~0). 0.0 if undefined."""
    r = pd.Series(daily_returns).dropna()
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(np.sqrt(periods) * r.mean() / r.std(ddof=1))


def annualized_sortino(daily_returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized Sortino ratio (downside deviation). 0.0 if undefined."""
    r = pd.Series(daily_returns).dropna()
    downside = r[r < 0]
    if len(r) < 2 or len(downside) < 1 or downside.std(ddof=1) == 0:
        return 0.0
    return float(np.sqrt(periods) * r.mean() / downside.std(ddof=1))


def buy_and_hold_return(close: pd.Series) -> float:
    """Total return of buying the first bar and holding to the last."""
    c = pd.Series(close).dropna()
    if len(c) < 2 or c.iloc[0] == 0:
        return 0.0
    return float(c.iloc[-1] / c.iloc[0] - 1.0)


def expectancy(trade_returns) -> float:
    """Mean per-trade return (the average edge realized per trade)."""
    r = pd.Series(trade_returns, dtype=float)
    return float(r.mean()) if len(r) else 0.0


def profit_factor(trade_returns) -> float:
    """Gross wins / gross losses. ``inf`` if no losses, ``0`` if no wins."""
    r = pd.Series(trade_returns, dtype=float)
    wins = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses)


def t_stat(trade_returns) -> float:
    """One-sample t-statistic of per-trade returns vs 0 (edge significance)."""
    r = pd.Series(trade_returns, dtype=float).dropna()
    std = r.std(ddof=1)
    if len(r) < 2 or std < 1e-12:
        return 0.0
    return float(r.mean() / (std / np.sqrt(len(r))))


def bootstrap_ci(
    trade_returns, *, n: int = 10_000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float]:
    """Bootstrap CI for the mean per-trade return. Edge is 'real-ish' if it excludes 0."""
    r = pd.Series(trade_returns, dtype=float).dropna().to_numpy()
    if len(r) < 2:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    means = rng.choice(r, size=(n, len(r)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def percentile_rank(value: float, distribution) -> float:
    """Fraction of the distribution that ``value`` exceeds, in [0, 1].

    Used to score a strategy against a null (e.g. random-entry) distribution:
    0.95 means it beat 95% of the null runs.
    """
    d = pd.Series(distribution, dtype=float).dropna().to_numpy()
    if len(d) == 0:
        return 0.0
    return float((d < value).mean())


def train_test_split(
    bars: dict[str, pd.DataFrame], split: str
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Split each symbol's bars into in-sample (< split) and out-of-sample (>= split).

    The cornerstone of honest backtesting: tune on train, judge on test.
    """
    cutoff = pd.Timestamp(split)
    train = {s: df.loc[df.index < cutoff] for s, df in bars.items()}
    test = {s: df.loc[df.index >= cutoff] for s, df in bars.items()}
    train = {s: df for s, df in train.items() if not df.empty}
    test = {s: df for s, df in test.items() if not df.empty}
    return train, test
