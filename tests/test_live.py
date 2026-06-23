"""Tests for Phase 7 the autonomous runner, driven by SimBroker (no network)."""

import pandas as pd

from autotrader.config import RiskLimits
from autotrader.execution.broker import Order
from autotrader.execution.sim import SimBroker
from autotrader.live.runner import TradingEngine, _OpenPlan
from autotrader.strategy.base import Side, Signal


def _frame(prices, *, high_mult=1.0, low_mult=1.0):
    idx = pd.date_range("2024-01-01", periods=len(prices))
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * high_mult,
            "low": close * low_mult,
            "close": close,
            "volume": 10_000,
        },
        index=idx,
    )


class _FakeStrategy:
    """Returns a fixed SignalSet, so engine behavior is tested in isolation."""

    name = "fake"

    def __init__(self, signals):
        self._signals = signals

    def generate(self, bars):
        return self._signals


def _buy_signal_on_last_bar(df, symbol, *, stop=95.0, target=110.0, max_hold=2):
    return Signal(
        symbol=symbol,
        timestamp=df.index[-1],
        side=Side.BUY,
        stop_loss=stop,
        take_profit=target,
        max_hold_days=max_hold,
    )


def test_entry_places_sized_order_and_journals():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    strat = _FakeStrategy({"AAA": [_buy_signal_on_last_bar(df, "AAA")]})

    engine = TradingEngine(broker, strat, bar_loader=lambda: {"AAA": df})
    summary = engine.run_once()

    pos = broker.get_positions()
    assert summary["entries"] == 1
    # risk 1% of 10k = $100 over $5 stop distance = 20 shares; capped at 10% notional = 10.
    assert pos[0].symbol == "AAA" and pos[0].qty == 10
    assert engine.journal[-1]["action"] == "entry"


def test_no_pyramiding_into_existing_position():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    strat = _FakeStrategy({"AAA": [_buy_signal_on_last_bar(df, "AAA")]})
    engine = TradingEngine(broker, strat, bar_loader=lambda: {"AAA": df})

    engine.run_once()
    engine.run_once()  # same bar, signal still present -> must not add shares

    assert broker.get_positions()[0].qty == 10


def test_halted_engine_places_nothing():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    strat = _FakeStrategy({"AAA": [_buy_signal_on_last_bar(df, "AAA")]})
    engine = TradingEngine(broker, strat, bar_loader=lambda: {"AAA": df}, halted=True)

    engine.run_once()
    assert broker.get_positions() == []


def test_max_concurrent_positions_caps_entries():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=100_000)
    signals = {}
    loader = {}
    for sym in [f"S{i}" for i in range(7)]:
        broker.set_price(sym, 100.0)
        signals[sym] = [_buy_signal_on_last_bar(df, sym)]
        loader[sym] = df
    limits = RiskLimits(max_concurrent_positions=5)
    engine = TradingEngine(broker, _FakeStrategy(signals), bar_loader=lambda: loader, limits=limits)

    engine.run_once()
    assert len(broker.get_positions()) == 5


def test_exit_on_max_hold():
    df = _frame([100.0] * 5)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    broker.submit_order(Order("AAA", 10, Side.BUY, "seed"))
    engine = TradingEngine(broker, _FakeStrategy({}), bar_loader=lambda: {"AAA": df})
    # Entered three bars ago with a 1-day max hold -> must exit now.
    engine._plans["AAA"] = _OpenPlan(
        entry_date=df.index[-3], stop=90.0, target=200.0, max_hold=1
    )

    engine.run_once()
    assert broker.get_positions() == []
    assert engine.journal[-1]["reason"] == "max_hold"


def test_exit_on_stop_hit():
    df = _frame([100.0] * 5, low_mult=0.90)  # last bar low = 90
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    broker.submit_order(Order("AAA", 10, Side.BUY, "seed"))
    engine = TradingEngine(broker, _FakeStrategy({}), bar_loader=lambda: {"AAA": df})
    engine._plans["AAA"] = _OpenPlan(
        entry_date=df.index[-1], stop=95.0, target=200.0, max_hold=10
    )

    engine.run_once()
    assert broker.get_positions() == []
    assert engine.journal[-1]["reason"] == "stop"


def test_unknown_position_closed_defensively():
    df = _frame([100.0] * 5)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    broker.submit_order(Order("AAA", 10, Side.BUY, "seed"))  # no plan recorded
    engine = TradingEngine(broker, _FakeStrategy({}), bar_loader=lambda: {"AAA": df})

    engine.run_once()
    assert broker.get_positions() == []
    assert engine.journal[-1]["reason"] == "unknown_position"
