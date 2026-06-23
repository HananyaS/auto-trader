"""Configuration & secrets loading.

Loads settings from environment variables (optionally via a local ``.env`` file).
Secrets (API keys) are NEVER hardcoded or committed — see ``.env.example``.

Usage:
    from autotrader.config import Settings
    settings = Settings.from_env()
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # python-dotenv is optional at import time; .env is convenience only.
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv not installed yet
    pass


# Alpaca REST endpoints. Paper and live share the same SDK; only the base URL
# and credentials differ, so the rest of the codebase stays identical.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL = "https://api.alpaca.markets"


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else int(raw)


@dataclass(frozen=True)
class RiskLimits:
    """Hard guardrails enforced by the risk layer (PDT-aware, <$25k account)."""

    risk_per_trade: float = 0.01
    max_position_pct: float = 0.10
    max_concurrent_positions: int = 5
    max_portfolio_exposure: float = 0.60
    daily_max_loss: float = 0.03
    pdt_max_day_trades: int = 3

    @classmethod
    def from_env(cls) -> RiskLimits:
        return cls(
            risk_per_trade=_get_float("RISK_PER_TRADE", 0.01),
            max_position_pct=_get_float("MAX_POSITION_PCT", 0.10),
            max_concurrent_positions=_get_int("MAX_CONCURRENT_POSITIONS", 5),
            max_portfolio_exposure=_get_float("MAX_PORTFOLIO_EXPOSURE", 0.60),
            daily_max_loss=_get_float("DAILY_MAX_LOSS", 0.03),
            pdt_max_day_trades=_get_int("PDT_MAX_DAY_TRADES", 3),
        )


@dataclass(frozen=True)
class Settings:
    """Top-level runtime configuration."""

    alpaca_api_key: str
    alpaca_secret_key: str
    alpaca_env: str  # "paper" or "live"
    risk: RiskLimits

    @property
    def is_paper(self) -> bool:
        return self.alpaca_env.lower() != "live"

    @property
    def alpaca_base_url(self) -> str:
        return PAPER_BASE_URL if self.is_paper else LIVE_BASE_URL

    @classmethod
    def from_env(cls) -> Settings:
        env = os.getenv("ALPACA_ENV", "paper").lower()
        if env not in {"paper", "live"}:
            raise ValueError(f"ALPACA_ENV must be 'paper' or 'live', got {env!r}")
        return cls(
            alpaca_api_key=os.getenv("ALPACA_API_KEY", ""),
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", ""),
            alpaca_env=env,
            risk=RiskLimits.from_env(),
        )

    def require_credentials(self) -> None:
        """Raise if Alpaca credentials are missing. Call before hitting the API."""
        missing = [
            name
            for name, val in (
                ("ALPACA_API_KEY", self.alpaca_api_key),
                ("ALPACA_SECRET_KEY", self.alpaca_secret_key),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"Missing required env vars: {', '.join(missing)}. "
                "Copy .env.example to .env and fill them in."
            )
