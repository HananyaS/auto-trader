"""Alpaca adapter implementing the ``Broker`` interface (Phase 6, see ROADMAP.md).

Paper and live differ only by credentials/endpoint (see ``Settings``), so the rest
of the system is identical across both. Idempotency rides on Alpaca's unique
``client_order_id`` — resubmitting the same id is rejected by the API rather than
creating a duplicate, which is what makes restarts safe.

The ``alpaca`` SDK is imported lazily so this module (and the test suite) load
without the dependency or any network access.
"""

from __future__ import annotations

from autotrader.config import Settings
from autotrader.execution.broker import Order, Position
from autotrader.strategy.base import Side


class AlpacaBroker:
    """Live/paper broker backed by alpaca-py's TradingClient."""

    def __init__(self, settings: Settings) -> None:
        # Fail fast on missing creds *before* importing the SDK.
        settings.require_credentials()
        from alpaca.trading.client import TradingClient

        self._client = TradingClient(
            settings.alpaca_api_key,
            settings.alpaca_secret_key,
            paper=settings.is_paper,
        )

    def get_account(self) -> dict:
        a = self._client.get_account()
        return {
            "cash": float(a.cash),
            "equity": float(a.equity),
            "buying_power": float(a.buying_power),
            "daytrade_count": int(a.daytrade_count),
            "pattern_day_trader": bool(a.pattern_day_trader),
        }

    def get_positions(self) -> list[Position]:
        return [
            Position(p.symbol, int(float(p.qty)), float(p.avg_entry_price))
            for p in self._client.get_all_positions()
        ]

    def submit_order(self, order: Order) -> str:
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        side = OrderSide.BUY if order.side is Side.BUY else OrderSide.SELL
        common = dict(
            symbol=order.symbol,
            qty=order.qty,
            side=side,
            time_in_force=TimeInForce.DAY,
            client_order_id=order.client_order_id,  # idempotency key
        )
        if order.order_type == "limit":
            req = LimitOrderRequest(limit_price=order.limit_price, **common)
        else:
            req = MarketOrderRequest(**common)
        return str(self._client.submit_order(req).id)

    def cancel(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)
