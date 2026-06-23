"""Hard risk guardrails enforced before any order is placed (Phase 5, see ROADMAP.md).

A global halt flag, daily-loss kill-switch, max concurrent positions, max exposure,
and PDT-awareness (accounts <$25k are capped at a few day-trades per 5 sessions).
A 1-2 day *hold* usually avoids same-day round-trips, but we track day-trades so the
bot never gets locked out.
"""

from __future__ import annotations

from dataclasses import dataclass

from autotrader.config import RiskLimits


@dataclass
class RiskState:
    """Live counters the guardrails check against (updated each session)."""

    open_positions: int = 0
    portfolio_exposure: float = 0.0  # fraction of equity currently deployed
    day_trades_used: int = 0  # rolling 5-session count, for PDT
    day_pnl_pct: float = 0.0  # today's P&L as a fraction of equity (negative = loss)
    halted: bool = False


def daily_loss_breached(state: RiskState, limits: RiskLimits) -> bool:
    """True once today's loss hits the kill-switch threshold."""
    return state.day_pnl_pct <= -abs(limits.daily_max_loss)


def would_breach_pdt(state: RiskState, limits: RiskLimits) -> bool:
    """True if making one more day-trade would exceed the PDT cap (<$25k accounts)."""
    return state.day_trades_used >= limits.pdt_max_day_trades


def can_open_new_position(state: RiskState, limits: RiskLimits) -> bool:
    """Whether a new entry is permitted right now under all guardrails."""
    if state.halted:
        return False
    if daily_loss_breached(state, limits):
        return False
    if state.open_positions >= limits.max_concurrent_positions:
        return False
    if state.portfolio_exposure >= limits.max_portfolio_exposure:
        return False
    return True
