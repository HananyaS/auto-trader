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
