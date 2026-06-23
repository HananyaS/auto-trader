"""Broker-agnostic execution interface.

Phase 6 (see ROADMAP.md). The Alpaca adapter (paper endpoint first) implements
this Protocol. Real-world concerns handled by implementations: order types,
idempotency (no duplicate orders on restart), state reconciliation on startup,
retries on transient errors, and partial fills.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from autotrader.strategy.base import Side


@dataclass(frozen=True)
class Order:
    symbol: str
    qty: int
    side: Side
    client_order_id: str  # for idempotency: same id => never double-submit
    order_type: str = "market"  # "market" or "limit"
    limit_price: float | None = None


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: int
    avg_entry_price: float


class Broker(Protocol):
    """Common surface the runner depends on; swap paper<->live via config only."""

    def get_account(self) -> dict: ...
    def get_positions(self) -> list[Position]: ...
    def submit_order(self, order: Order) -> str: ...
    def cancel(self, order_id: str) -> None: ...
