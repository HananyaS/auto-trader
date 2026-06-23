"""backtrader-based backtest runner (Phase 4, see ROADMAP.md) — the make-or-break step.

Bridges the pure-function strategies (``Strategy.generate(bars) -> SignalSet``) into a
backtrader ``Cerebro``: signals are precomputed, then a thin backtrader strategy acts on
them bar-by-bar. Entries are submitted as market orders (filled at the *next* bar's open,
so there is no look-ahead). Exits honor the per-signal stop-loss, take-profit, and
``max_hold_days`` for the 1-2 day horizon.

Costs are modeled realistically: commission (~0 on Alpaca) plus percentage slippage that
stands in for the bid/ask spread. Metrics (Sharpe, Sortino, max drawdown, win rate, trade
count) come from a mix of backtrader analyzers and our pure ``metrics`` helpers.
"""

from __future__ import annotations

from dataclasses import dataclass

import backtrader as bt
import pandas as pd

from autotrader.backtest.metrics import annualized_sharpe, annualized_sortino
from autotrader.config import RiskLimits
from autotrader.risk.sizing import position_size
from autotrader.strategy.base import Side, Signal, SignalSet, Strategy


@dataclass(frozen=True)
class BacktestResult:
    """Headline metrics from a single backtest run."""

    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    num_trades: int
    final_value: float


def _index_signals_by_date(signals: SignalSet) -> dict[str, dict[object, Signal]]:
    """{symbol: {date: Signal}} keyed by calendar date for O(1) lookup in next()."""
    indexed: dict[str, dict[object, Signal]] = {}
    for symbol, sigs in signals.items():
        per_day: dict[object, Signal] = {}
        for sig in sigs:
            per_day[pd.Timestamp(sig.timestamp).date()] = sig  # last wins
        indexed[symbol] = per_day
    return indexed


class _SignalDriven(bt.Strategy):
    """Acts on precomputed entry signals; manages stop/target/time exits per symbol."""

    params = dict(signals={}, limits=None, alloc_pct=0.1)

    def __init__(self) -> None:
        self._sig = _index_signals_by_date(self.p.signals)
        self._limits = self.p.limits
        # Per-data exit bookkeeping: data -> (entry_bar, stop, target, max_hold).
        self._open: dict[object, tuple[int, float, float, int]] = {}

    def next(self) -> None:
        for data in self.datas:
            symbol = data._name
            today = data.datetime.date(0)
            pos = self.getposition(data)

            if not pos.size:
                sig = self._sig.get(symbol, {}).get(today)
                if sig is not None and sig.side is Side.BUY:
                    self._try_enter(data, sig)
            else:
                self._manage_exit(data)

    def _try_enter(self, data, sig: Signal) -> None:
        price = data.close[0]
        equity = self.broker.getvalue()
        # Shared sizer when the signal carries a valid stop; alloc fallback otherwise.
        if self._limits is not None and sig.stop_loss is not None and sig.stop_loss < price:
            size = position_size(equity, price, sig.stop_loss, self._limits)
        else:
            size = int((equity * self.p.alloc_pct) / price)
        if size < 1:
            return
        self.buy(data=data, size=size)
        stop = sig.stop_loss if sig.stop_loss is not None else 0.0
        target = sig.take_profit if sig.take_profit is not None else float("inf")
        self._open[data] = (len(data), stop, target, sig.max_hold_days)

    def _manage_exit(self, data) -> None:
        info = self._open.get(data)
        if info is None:
            return
        entry_bar, stop, target, max_hold = info
        held = len(data) - entry_bar
        hit_stop = data.low[0] <= stop
        hit_target = data.high[0] >= target
        if hit_stop or hit_target or held >= max_hold:
            self.close(data=data)
            self._open.pop(data, None)


def run_backtest(
    bars: dict[str, pd.DataFrame],
    strategy: Strategy,
    *,
    starting_cash: float = 10_000.0,
    commission: float = 0.0,
    slippage_perc: float = 0.0005,
    limits: RiskLimits | None = None,
    alloc_pct: float = 0.1,
) -> BacktestResult:
    """Run ``strategy`` over ``bars`` and return headline metrics.

    Sizing uses the shared risk sizer (``limits``, default ``RiskLimits()``) so the
    backtest sizes positions exactly as live will; ``alloc_pct`` is a fallback when a
    signal lacks a stop.
    """
    signals = strategy.generate(bars)
    limits = limits or RiskLimits()

    cerebro = bt.Cerebro(stdstats=False)
    for symbol, df in bars.items():
        feed = bt.feeds.PandasData(dataname=df, openinterest=-1)
        cerebro.adddata(feed, name=symbol)

    cerebro.addstrategy(_SignalDriven, signals=signals, limits=limits, alloc_pct=alloc_pct)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(commission=commission)
    if slippage_perc:
        cerebro.broker.set_slippage_perc(perc=slippage_perc)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, timeframe=bt.TimeFrame.Days, _name="treturn")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    strat = cerebro.run()[0]
    final_value = float(cerebro.broker.getvalue())

    daily = pd.Series(strat.analyzers.treturn.get_analysis())
    dd = strat.analyzers.dd.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    total = trades.get("total", {}).get("closed", 0) or 0
    won = trades.get("won", {}).get("total", 0) or 0
    win_rate = (won / total) if total else 0.0

    return BacktestResult(
        total_return=final_value / starting_cash - 1.0,
        sharpe=annualized_sharpe(daily),
        sortino=annualized_sortino(daily),
        max_drawdown=float(dd.get("max", {}).get("drawdown", 0.0)) / 100.0,
        win_rate=win_rate,
        num_trades=int(total),
        final_value=final_value,
    )
