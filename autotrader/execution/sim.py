"""In-memory simulated broker implementing the ``Broker`` interface.

Not a backtester — it's a deterministic stand-in for the live Alpaca broker used
in tests and dry-runs (Phase 6/7/8). Market orders fill immediately at the symbol's
current mark; orders are idempotent on ``client_order_id`` so a crash/restart that
resubmits the same intent never double-trades.
"""

from __future__ import annotations

import uuid

from autotrader.execution.broker import Order, Position
from autotrader.strategy.base import Side


class SimBroker:
    """Deterministic, in-memory broker for tests and dry-runs."""

    def __init__(self, cash: float = 10_000.0) -> None:
        self._cash = cash
        self._positions: dict[str, Position] = {}
        self._prices: dict[str, float] = {}
        # client_order_id -> broker order id, for idempotency.
        self._submitted: dict[str, str] = {}

    # --- test/dry-run helpers (not part of the Broker protocol) ---

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = price

    # --- Broker protocol ---

    def get_account(self) -> dict:
        return {"cash": self._cash, "equity": self._equity(), "positions": len(self._positions)}

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def submit_order(self, order: Order) -> str:
        # Idempotency: same client_order_id is a no-op returning the original id.
        if order.client_order_id in self._submitted:
            return self._submitted[order.client_order_id]

        price = order.limit_price if order.order_type == "limit" else self._prices.get(order.symbol)
        if price is None:
            raise ValueError(f"no price set for {order.symbol}; call set_price() first")

        if order.side is Side.BUY:
            self._fill_buy(order.symbol, order.qty, price)
        else:
            self._fill_sell(order.symbol, order.qty, price)

        order_id = str(uuid.uuid4())
        self._submitted[order.client_order_id] = order_id
        return order_id

    def cancel(self, order_id: str) -> None:
        # Sim fills synchronously, so there is nothing pending to cancel.
        return None

    # --- internals ---

    def _equity(self) -> float:
        holdings = sum(
            p.qty * self._prices.get(s, p.avg_entry_price)
            for s, p in self._positions.items()
        )
        return self._cash + holdings

    def _fill_buy(self, symbol: str, qty: int, price: float) -> None:
        self._cash -= qty * price
        existing = self._positions.get(symbol)
        if existing is None:
            self._positions[symbol] = Position(symbol, qty, price)
        else:
            total_qty = existing.qty + qty
            avg = (existing.qty * existing.avg_entry_price + qty * price) / total_qty
            self._positions[symbol] = Position(symbol, total_qty, avg)

    def _fill_sell(self, symbol: str, qty: int, price: float) -> None:
        self._cash += qty * price
        existing = self._positions.get(symbol)
        if existing is None:
            return
        remaining = existing.qty - qty
        if remaining <= 0:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = Position(symbol, remaining, existing.avg_entry_price)
