"""Tests for Phase 6 execution: SimBroker behavior + AlpacaBroker creds guard.

No network: SimBroker is in-memory, and the AlpacaBroker test asserts the
credential check fires before the SDK is even imported.
"""

import pytest

from autotrader.config import RiskLimits, Settings
from autotrader.execution.alpaca import AlpacaBroker
from autotrader.execution.broker import Order
from autotrader.execution.sim import SimBroker
from autotrader.strategy.base import Side


def _order(symbol, qty, side, coid, **kw):
    return Order(symbol=symbol, qty=qty, side=side, client_order_id=coid, **kw)


def test_buy_updates_cash_and_position():
    b = SimBroker(cash=10_000)
    b.set_price("AAPL", 100.0)
    b.submit_order(_order("AAPL", 10, Side.BUY, "c1"))

    acct = b.get_account()
    assert acct["cash"] == 9_000
    pos = b.get_positions()
    assert len(pos) == 1
    assert pos[0].symbol == "AAPL" and pos[0].qty == 10 and pos[0].avg_entry_price == 100.0


def test_buy_averages_entry_price():
    b = SimBroker(cash=10_000)
    b.set_price("AAPL", 100.0)
    b.submit_order(_order("AAPL", 10, Side.BUY, "c1"))
    b.set_price("AAPL", 120.0)
    b.submit_order(_order("AAPL", 10, Side.BUY, "c2"))

    pos = b.get_positions()[0]
    assert pos.qty == 20
    assert pos.avg_entry_price == 110.0  # (10*100 + 10*120) / 20


def test_sell_closes_position():
    b = SimBroker(cash=10_000)
    b.set_price("AAPL", 100.0)
    b.submit_order(_order("AAPL", 10, Side.BUY, "c1"))
    b.submit_order(_order("AAPL", 10, Side.SELL, "c2"))

    assert b.get_positions() == []
    assert b.get_account()["cash"] == 10_000  # round-trip at the same price


def test_submit_is_idempotent_on_client_order_id():
    b = SimBroker(cash=10_000)
    b.set_price("AAPL", 100.0)
    first = b.submit_order(_order("AAPL", 10, Side.BUY, "dup"))
    # Resubmitting the same client_order_id must NOT trade again (restart safety).
    second = b.submit_order(_order("AAPL", 10, Side.BUY, "dup"))

    assert first == second
    assert b.get_positions()[0].qty == 10  # still only 10, not 20
    assert b.get_account()["cash"] == 9_000


def test_market_order_without_price_raises():
    b = SimBroker()
    with pytest.raises(ValueError, match="no price set"):
        b.submit_order(_order("AAPL", 1, Side.BUY, "c1"))


def test_limit_order_fills_at_limit_price():
    b = SimBroker(cash=10_000)
    b.submit_order(_order("AAPL", 10, Side.BUY, "c1", order_type="limit", limit_price=90.0))
    assert b.get_account()["cash"] == 9_100  # filled at the limit, not a mark


def test_alpaca_broker_requires_credentials_before_sdk_import():
    settings = Settings(
        alpaca_api_key="", alpaca_secret_key="", alpaca_env="paper", risk=RiskLimits()
    )
    with pytest.raises(RuntimeError, match="Missing required env vars"):
        AlpacaBroker(settings)
