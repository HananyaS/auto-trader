"""Position sizing, shared by backtest and live.

Phase 5 (see ROADMAP.md). Fixed-fractional by default (risk_per_trade of equity),
optionally volatility-adjusted. Same function drives simulated and real sizing.
"""

from __future__ import annotations

from autotrader.config import RiskLimits


def position_size(
    equity: float,
    entry_price: float,
    stop_price: float,
    limits: RiskLimits,
) -> int:
    """Return share quantity for a trade given risk limits.

    TODO(Phase 5): risk = equity * risk_per_trade; qty = risk / (entry - stop),
    then clamp by max_position_pct. Returns whole shares (no fractional for now).
    """
    raise NotImplementedError("Phase 5: implement position sizing")
