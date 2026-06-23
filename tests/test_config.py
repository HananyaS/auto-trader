"""Tests for the config / secrets layer (Phase 1)."""

import pytest

from autotrader.config import (
    LIVE_BASE_URL,
    PAPER_BASE_URL,
    RiskLimits,
    Settings,
)


def test_defaults_are_paper_and_pdt_aware(monkeypatch):
    # Clear any ambient config so we test true defaults.
    for var in (
        "ALPACA_API_KEY",
        "ALPACA_SECRET_KEY",
        "ALPACA_ENV",
        "RISK_PER_TRADE",
        "MAX_POSITION_PCT",
        "MAX_CONCURRENT_POSITIONS",
        "MAX_PORTFOLIO_EXPOSURE",
        "DAILY_MAX_LOSS",
        "PDT_MAX_DAY_TRADES",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings.from_env()

    assert settings.is_paper is True
    assert settings.alpaca_base_url == PAPER_BASE_URL
    assert settings.risk == RiskLimits()  # all defaults
    assert settings.risk.pdt_max_day_trades == 3  # PDT-aware default


def test_live_env_uses_live_url(monkeypatch):
    monkeypatch.setenv("ALPACA_ENV", "live")
    settings = Settings.from_env()
    assert settings.is_paper is False
    assert settings.alpaca_base_url == LIVE_BASE_URL


def test_invalid_env_rejected(monkeypatch):
    monkeypatch.setenv("ALPACA_ENV", "production")
    with pytest.raises(ValueError):
        Settings.from_env()


def test_risk_limits_read_from_env(monkeypatch):
    monkeypatch.setenv("RISK_PER_TRADE", "0.02")
    monkeypatch.setenv("MAX_CONCURRENT_POSITIONS", "8")
    limits = RiskLimits.from_env()
    assert limits.risk_per_trade == 0.02
    assert limits.max_concurrent_positions == 8


def test_require_credentials_raises_when_missing(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    settings = Settings.from_env()
    with pytest.raises(RuntimeError, match="Missing required env vars"):
        settings.require_credentials()
