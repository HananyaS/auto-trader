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

import logging
from dataclasses import dataclass

import backtrader as bt
import pandas as pd

from autotrader.backtest.metrics import (
    annualized_sharpe,
    annualized_sortino,
    expectancy,
    profit_factor,
)
from autotrader.config import RiskLimits
from autotrader.risk.sizing import position_size
from autotrader.strategy.base import Side, Signal, SignalSet, Strategy

log = logging.getLogger("autotrader.backtest")


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
    # Fair-comparison + edge-detection extras (defaulted; older callers unaffected).
    exposure: float = 0.0  # avg fraction of equity deployed (cash drag indicator)
    expectancy: float = 0.0  # mean per-trade return
    profit_factor: float = 0.0  # gross wins / gross losses
    trade_returns: tuple[float, ...] = ()  # per-closed-trade returns (for significance)

    @property
    def return_on_exposure(self) -> float:
        """Total return normalized by average exposure (undoes cash drag)."""
        return self.total_return / self.exposure if self.exposure > 1e-9 else 0.0


class _ExposureAnalyzer(bt.Analyzer):
    """Average fraction of account equity deployed in positions, across all bars."""

    def __init__(self) -> None:
        self._frac_sum = 0.0
        self._bars = 0

    def next(self) -> None:
        value = self.strategy.broker.getvalue()
        if value <= 0:
            return
        deployed = sum(
            self.strategy.getposition(d).size * d.close[0] for d in self.strategy.datas
        )
        self._frac_sum += deployed / value
        self._bars += 1

    def get_analysis(self):
        return {"exposure": (self._frac_sum / self._bars) if self._bars else 0.0}


class _TradeReturns(bt.Analyzer):
    """Per-closed-trade percentage returns: pnlcomm / entry notional.

    The entry notional is captured on open (a closed trade reports size 0), keyed
    by trade ref, then consumed when the trade closes.
    """

    def __init__(self) -> None:
        self._returns: list[float] = []
        self._basis: dict[int, float] = {}

    def notify_trade(self, trade) -> None:
        if trade.justopened:
            self._basis[trade.ref] = abs(trade.price * trade.size)
        if trade.isclosed:
            basis = self._basis.pop(trade.ref, None)
            if basis:
                self._returns.append(trade.pnlcomm / basis)

    def get_analysis(self):
        return {"returns": list(self._returns)}


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
    feeds_added = 0
    for symbol, df in bars.items():
        # An empty/degenerate feed makes backtrader's next() never fire, silently
        # halting the *whole* run, so skip such symbols defensively.
        if df is None or len(df) < 2:
            log.warning("skipping %s: only %d bar(s)", symbol, 0 if df is None else len(df))
            continue
        cerebro.adddata(bt.feeds.PandasData(dataname=df, openinterest=-1), name=symbol)
        feeds_added += 1
    if feeds_added == 0:
        raise ValueError("no usable data feeds (all symbols empty/too short)")
    cerebro.addstrategy(_SignalDriven, signals=signals, limits=limits, alloc_pct=alloc_pct)
    cerebro.broker.setcash(starting_cash)
    cerebro.broker.setcommission(commission=commission)
    if slippage_perc:
        cerebro.broker.set_slippage_perc(perc=slippage_perc)

    cerebro.addanalyzer(bt.analyzers.TimeReturn, timeframe=bt.TimeFrame.Days, _name="treturn")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(_ExposureAnalyzer, _name="exposure")
    cerebro.addanalyzer(_TradeReturns, _name="tradereturns")

    strat = cerebro.run()[0]
    final_value = float(cerebro.broker.getvalue())

    daily = pd.Series(strat.analyzers.treturn.get_analysis())
    dd = strat.analyzers.dd.get_analysis()
    trades = strat.analyzers.trades.get_analysis()
    exposure = float(strat.analyzers.exposure.get_analysis()["exposure"])
    trade_returns = tuple(strat.analyzers.tradereturns.get_analysis()["returns"])

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
        exposure=exposure,
        expectancy=expectancy(trade_returns),
        profit_factor=profit_factor(trade_returns),
        trade_returns=trade_returns,
    )
