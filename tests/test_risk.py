"""Tests for Phase 5 risk management: position sizing + guardrails."""

import pytest

from autotrader.config import RiskLimits
from autotrader.risk.limits import (
    RiskState,
    can_open_new_position,
    daily_loss_breached,
    would_breach_pdt,
)
from autotrader.risk.sizing import position_size

LIMITS = RiskLimits()  # defaults: risk 1%, max position 10%, 5 positions, PDT 3


# --- sizing -------------------------------------------------------------------


def test_position_size_uses_risk_budget():
    # equity 10k, risk 1% = $100; per-share risk = 100-95 = 5 -> 20 shares.
    # cap: 10% notional = $1000 / 100 = 10 shares -> the cap binds, so 10.
    assert position_size(10_000, 100.0, 95.0, LIMITS) == 10


def test_position_size_risk_budget_binds_with_tight_stop():
    # per-share risk = 100-99 = 1 -> risk budget allows 100 shares,
    # but cap is 10 shares -> cap binds.
    assert position_size(10_000, 100.0, 99.0, LIMITS) == 10


def test_position_size_risk_binds_with_wide_stop():
    # wide stop: per-share risk = 100-50 = 50 -> 100/50 = 2 shares (risk binds
    # below the 10-share cap).
    assert position_size(10_000, 100.0, 50.0, LIMITS) == 2


def test_position_size_rejects_stop_at_or_above_entry():
    with pytest.raises(ValueError, match="must be below entry_price"):
        position_size(10_000, 100.0, 100.0, LIMITS)


def test_position_size_zero_for_degenerate_inputs():
    assert position_size(0, 100.0, 95.0, LIMITS) == 0
    assert position_size(10_000, 0.0, -1.0, LIMITS) == 0


# --- guardrails ---------------------------------------------------------------


def test_can_open_when_state_clean():
    assert can_open_new_position(RiskState(), LIMITS) is True


def test_halt_flag_blocks_entry():
    assert can_open_new_position(RiskState(halted=True), LIMITS) is False


def test_daily_loss_kill_switch():
    state = RiskState(day_pnl_pct=-0.03)  # at the -3% default threshold
    assert daily_loss_breached(state, LIMITS) is True
    assert can_open_new_position(state, LIMITS) is False


def test_max_concurrent_positions_blocks_entry():
    state = RiskState(open_positions=LIMITS.max_concurrent_positions)
    assert can_open_new_position(state, LIMITS) is False


def test_max_exposure_blocks_entry():
    state = RiskState(portfolio_exposure=LIMITS.max_portfolio_exposure)
    assert can_open_new_position(state, LIMITS) is False


def test_pdt_guard():
    assert would_breach_pdt(RiskState(day_trades_used=2), LIMITS) is False
    assert would_breach_pdt(RiskState(day_trades_used=3), LIMITS) is True
