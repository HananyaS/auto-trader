"""Hard risk guardrails enforced before any order is placed.

Phase 5 (see ROADMAP.md). Per-trade stop, daily-loss kill-switch, max concurrent
positions, max exposure, global halt flag, and PDT-awareness (accounts <$25k are
limited to a few day-trades per 5 sessions). A 1-2 day hold usually avoids same-day
round-trips, but we track day-trades so the bot never gets locked.
"""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.config import RiskLimits


@dataclass
class RiskState:
    """Live counters the guardrails check against (updated each session)."""

    open_positions: int = 0
    portfolio_exposure: float = 0.0
    day_trades_used: int = 0  # rolling 5-session count, for PDT
    day_pnl_pct: float = 0.0
    halted: bool = False


def can_open_new_position(state: RiskState, limits: RiskLimits) -> bool:
    """TODO(Phase 5): check halt flag, position count, exposure, daily loss, PDT."""
    raise NotImplementedError("Phase 5: implement guardrail checks")


def would_breach_pdt(state: RiskState, limits: RiskLimits) -> bool:
    """TODO(Phase 5): true if opening+closing same session would exceed PDT cap."""
    raise NotImplementedError("Phase 5: implement PDT check")
