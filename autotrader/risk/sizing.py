"""Position sizing, shared by backtest and live (Phase 5, see ROADMAP.md).

Fixed-fractional risk model: risk a fixed fraction of equity per trade, derived
from the distance between entry and stop, then clamp by a max position size.
The *same* function drives simulated and real sizing so they can't diverge.
"""

from __future__ import annotations

import math

from autotrader.config import RiskLimits


def position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    limits: RiskLimits,
) -> int:
    """Whole-share quantity for a long trade.

    qty = (equity * risk_per_trade) / (entry - stop), then clamped so the
    position's notional never exceeds ``max_position_pct`` of equity. Returns 0
    if inputs are degenerate (non-positive equity/price).

    Raises:
        ValueError: if ``stop_price >= entry_price`` (no defined risk for a long).
    """
    if equity <= 0 or entry_price <= 0:
        return 0
    if stop_price >= entry_price:
        raise ValueError(
            f"stop_price ({stop_price}) must be below entry_price ({entry_price}) for a long"
        )

    per_share_risk = entry_price - stop_price
    risk_budget = equity * limits.risk_per_trade
    qty_by_risk = risk_budget / per_share_risk

    max_notional = equity * limits.max_position_pct
    qty_by_cap = max_notional / entry_price

    return max(0, math.floor(min(qty_by_risk, qty_by_cap)))
