"""backtrader-based backtest runner + metrics.

Phase 4 (see ROADMAP.md) — the make-or-break step. Must model costs realistically
(slippage + bid/ask spread + partial fills; commissions ~0 on Alpaca) and guard
against overfitting via walk-forward / out-of-sample splits. Reports Sharpe/Sortino,
max drawdown, win rate, exposure, turnover, and benchmarks vs buy-and-hold SPY.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestResult:
    """Headline metrics from a single backtest run (populated in Phase 4)."""

    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    num_trades: int


def run_backtest(*args, **kwargs) -> BacktestResult:
    """TODO(Phase 4): wire a Strategy into a backtrader Cerebro with realistic costs."""
    raise NotImplementedError("Phase 4: implement backtrader runner + metrics")
