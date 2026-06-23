"""Autonomous runner loop (Phase 7, see ROADMAP.md).

Each scheduled run executes one pass:

    reconcile with broker -> load bars -> manage exits -> generate signals
    -> apply risk guardrails + sizing -> place entries (idempotently)

``TradingEngine`` is dependency-injected (broker, strategy, bar loader, limits) so the
whole loop runs against ``SimBroker`` + synthetic bars in tests — no network. ``main()``
wires the real Alpaca broker + yfinance data + an APScheduler loop that respects the
market calendar.

Safety properties:
- Orders are idempotent on ``client_order_id`` (``{symbol}-{date}-entry|exit``), so a
  crash/restart that repeats a pass never double-trades.
- Positions are read back from the broker each pass (reconcile), so the engine never
  acts on stale internal state.
- A held position with no known exit plan (e.g. seen after a restart) is closed
  defensively — fitting for a 1-2 day horizon.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from autotrader.config import RiskLimits
from autotrader.execution.broker import Broker, Order
from autotrader.risk.limits import RiskState, can_open_new_position
from autotrader.risk.sizing import position_size
from autotrader.strategy.base import Side, Strategy

log = logging.getLogger("autotrader.live")

Bars = dict[str, pd.DataFrame]


@dataclass
class _OpenPlan:
    """Exit plan recorded when the engine opens a position."""

    entry_date: pd.Timestamp
    stop: float
    target: float
    max_hold: int


@dataclass
class TradingEngine:
    broker: Broker
    strategy: Strategy
    bar_loader: Callable[[], Bars]
    limits: RiskLimits = field(default_factory=RiskLimits)
    halted: bool = False

    def __post_init__(self) -> None:
        self._plans: dict[str, _OpenPlan] = {}
        self.journal: list[dict] = []

    def run_once(self) -> dict:
        """Execute one trading pass; returns a small summary for logging/tests."""
        bars = self.bar_loader()
        account = self.broker.get_account()
        equity = float(account.get("equity") or account.get("cash") or 0.0)

        exits = self._manage_exits(bars)
        entries = self._place_entries(bars, account, equity)

        summary = {"equity": equity, "entries": entries, "exits": exits}
        log.info("run_once: %s", summary)
        return summary

    # --- exits ---

    def _manage_exits(self, bars: Bars) -> int:
        count = 0
        for pos in self.broker.get_positions():
            df = bars.get(pos.symbol)
            if df is None or df.empty:
                continue
            last = df.iloc[-1]
            last_date = df.index[-1]
            plan = self._plans.get(pos.symbol)

            if plan is None:
                self._submit_exit(pos.symbol, pos.qty, last_date, "unknown_position")
                count += 1
                continue

            held = int((df.index > plan.entry_date).sum())
            if last["low"] <= plan.stop:
                reason = "stop"
            elif last["high"] >= plan.target:
                reason = "target"
            elif held >= plan.max_hold:
                reason = "max_hold"
            else:
                continue
            self._submit_exit(pos.symbol, pos.qty, last_date, reason)
            count += 1
        return count

    def _submit_exit(self, symbol: str, qty: int, last_date: pd.Timestamp, reason: str) -> None:
        coid = f"{symbol}-{last_date.date()}-exit"
        self.broker.submit_order(Order(symbol, qty, Side.SELL, coid))
        self._plans.pop(symbol, None)
        self._record("exit", symbol, qty, None, last_date, reason)

    # --- entries ---

    def _place_entries(self, bars: Bars, account: dict, equity: float) -> int:
        positions = {p.symbol: p for p in self.broker.get_positions()}
        state = RiskState(
            open_positions=len(positions),
            portfolio_exposure=self._exposure(positions, bars, equity),
            day_trades_used=int(account.get("daytrade_count", 0)),
            halted=self.halted,
        )

        signals = self.strategy.generate(bars)
        count = 0
        for symbol, sigs in signals.items():
            df = bars.get(symbol)
            if df is None or df.empty or symbol in positions:
                continue  # no data, or no pyramiding into an existing position
            last_date = df.index[-1]
            todays = [
                s for s in sigs if pd.Timestamp(s.timestamp) == last_date and s.side is Side.BUY
            ]
            if not todays:
                continue
            if not can_open_new_position(state, self.limits):
                break

            sig = todays[-1]
            price = float(df["close"].iloc[-1])
            if sig.stop_loss is None or sig.stop_loss >= price:
                continue
            qty = position_size(equity, price, sig.stop_loss, self.limits)
            if qty < 1:
                continue

            coid = f"{symbol}-{last_date.date()}-entry"
            self.broker.submit_order(Order(symbol, qty, Side.BUY, coid))
            self._plans[symbol] = _OpenPlan(
                entry_date=last_date,
                stop=sig.stop_loss,
                target=sig.take_profit if sig.take_profit is not None else float("inf"),
                max_hold=sig.max_hold_days,
            )
            state.open_positions += 1
            self._record("entry", symbol, qty, price, last_date, "signal")
            count += 1
        return count

    @staticmethod
    def _exposure(positions: dict, bars: Bars, equity: float) -> float:
        if equity <= 0:
            return 0.0
        notional = sum(
            p.qty * float(bars[s]["close"].iloc[-1]) for s, p in positions.items() if s in bars
        )
        return notional / equity

    def _record(self, action, symbol, qty, price, date, reason) -> None:
        self.journal.append(
            {
                "action": action,
                "symbol": symbol,
                "qty": qty,
                "price": price,
                "date": str(pd.Timestamp(date).date()),
                "reason": reason,
            }
        )


def main() -> None:  # pragma: no cover - wiring, exercised live not in tests
    """Entry point: build the real engine and schedule daily runs after the close."""
    import datetime as dt

    from apscheduler.schedulers.blocking import BlockingScheduler

    from autotrader.config import Settings
    from autotrader.data.loader import load_bars, sp500_symbols
    from autotrader.execution.alpaca import AlpacaBroker
    from autotrader.strategy.momentum import MomentumStrategy

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    universe = sp500_symbols()

    def bar_loader() -> Bars:
        end = dt.date.today()
        start = end - dt.timedelta(days=200)
        return load_bars(universe, start.isoformat(), end.isoformat())

    engine = TradingEngine(
        broker=AlpacaBroker(settings),
        strategy=MomentumStrategy(),
        bar_loader=bar_loader,
        limits=settings.risk,
    )

    scheduler = BlockingScheduler(timezone="America/New_York")

    @scheduler.scheduled_job("cron", day_of_week="mon-fri", hour=16, minute=10)
    def _job() -> None:
        if _is_trading_day(dt.date.today()):
            engine.run_once()

    log.info("scheduler starting (paper=%s)", settings.is_paper)
    scheduler.start()


def _is_trading_day(day) -> bool:  # pragma: no cover - thin calendar wrapper
    import pandas_market_calendars as mcal

    sched = mcal.get_calendar("XNYS").schedule(start_date=day, end_date=day)
    return not sched.empty
