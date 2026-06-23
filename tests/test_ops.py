"""Tests for Phase 8/9 ops enablement: notifier, journal, kill-switch, flatten, CLI."""

import json

import pandas as pd
import pytest

from autotrader.__main__ import build_parser
from autotrader.config import RiskLimits
from autotrader.execution.broker import Order
from autotrader.execution.sim import SimBroker
from autotrader.live.notify import TelegramNotifier
from autotrader.live.runner import TradingEngine
from autotrader.strategy.base import Side, Signal


def _frame(prices):
    idx = pd.date_range("2024-01-01", periods=len(prices))
    close = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": 1_000},
        index=idx,
    )


class _FakeStrategy:
    name = "fake"

    def __init__(self, signals):
        self._signals = signals

    def generate(self, bars):
        return self._signals


def _buy(df, symbol, stop=95.0):
    return Signal(
        symbol, df.index[-1], Side.BUY, stop_loss=stop, take_profit=110.0, max_hold_days=2
    )


# --- Telegram notifier --------------------------------------------------------


def test_telegram_builds_message_and_target(monkeypatch):
    sent = {}

    def fake_sender(url, payload):
        sent["url"] = url
        sent["payload"] = payload

    n = TelegramNotifier("TOKEN123", "CHAT9", sender=fake_sender)
    n.notify("hello")

    assert "TOKEN123" in sent["url"]
    assert sent["payload"] == {"chat_id": "CHAT9", "text": "hello"}


def test_telegram_requires_token_and_chat():
    with pytest.raises(ValueError):
        TelegramNotifier("", "chat")


# --- notifier wired into the engine -------------------------------------------


def test_engine_notifies_on_entry():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    messages = []

    class _N:
        def notify(self, m):
            messages.append(m)

    engine = TradingEngine(
        broker,
        _FakeStrategy({"AAA": [_buy(df, "AAA")]}),
        bar_loader=lambda: {"AAA": df},
        notifier=_N(),
    )
    engine.run_once()
    assert any(m.startswith("BUY") and "AAA" in m for m in messages)


def test_notifier_failure_does_not_crash_run(monkeypatch):
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)

    class _Boom:
        def notify(self, m):
            raise RuntimeError("telegram down")

    engine = TradingEngine(
        broker,
        _FakeStrategy({"AAA": [_buy(df, "AAA")]}),
        bar_loader=lambda: {"AAA": df},
        notifier=_Boom(),
    )
    # Must not raise despite the notifier blowing up.
    summary = engine.run_once()
    assert summary["entries"] == 1


# --- durable journal ----------------------------------------------------------


def test_journal_persists_to_jsonl(tmp_path):
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    path = tmp_path / "journal" / "trades.jsonl"

    engine = TradingEngine(
        broker,
        _FakeStrategy({"AAA": [_buy(df, "AAA")]}),
        bar_loader=lambda: {"AAA": df},
        journal_path=str(path),
    )
    engine.run_once()

    lines = path.read_text().strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["action"] == "entry" and rec["symbol"] == "AAA"


# --- kill-switch --------------------------------------------------------------


def test_daily_loss_kill_switch_halts_and_alerts():
    df = _frame([100.0] * 10)
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    messages = []

    class _N:
        def notify(self, m):
            messages.append(m)

    engine = TradingEngine(
        broker,
        _FakeStrategy({"AAA": [_buy(df, "AAA")]}),
        bar_loader=lambda: {"AAA": df},
        limits=RiskLimits(daily_max_loss=0.02),
        notifier=_N(),
    )
    engine.reset_day(equity=10_500)  # start-of-day above current -> a loss today
    engine.run_once()

    assert engine.halted is True
    assert broker.get_positions() == []  # no new entries while halted
    assert any("KILL-SWITCH" in m for m in messages)


# --- flatten all --------------------------------------------------------------


def test_flatten_all_closes_positions():
    broker = SimBroker(cash=10_000)
    broker.set_price("AAA", 100.0)
    broker.set_price("BBB", 50.0)
    broker.submit_order(Order("AAA", 5, Side.BUY, "a"))
    broker.submit_order(Order("BBB", 3, Side.BUY, "b"))

    engine = TradingEngine(broker, _FakeStrategy({}), bar_loader=lambda: {})
    closed = engine.flatten_all()

    assert closed == 2
    assert broker.get_positions() == []


# --- CLI parser ---------------------------------------------------------------


def test_cli_parses_backtest():
    args = build_parser().parse_args(
        ["backtest", "SPY", "QQQ", "--start", "2024-01-01", "--end", "2024-02-01"]
    )
    assert args.command == "backtest"
    assert args.symbols == ["SPY", "QQQ"]
    assert args.strategy == "momentum"


def test_cli_parses_run_and_flatten():
    assert build_parser().parse_args(["run", "--schedule"]).schedule is True
    assert build_parser().parse_args(["flatten"]).command == "flatten"
