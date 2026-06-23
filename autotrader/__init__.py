"""autotrader: autonomous short-term (1-2 day) stock/ETF trading system.

Subpackages map to the phases in ROADMAP.md:
    data       - market data fetch + caching
    strategy   - signal generation (entry/exit rules) as pure functions
    backtest   - historical simulation + metrics (backtrader-based)
    risk       - position sizing & risk limits (shared by backtest + live)
    execution  - broker adapter (Alpaca) behind a common interface
    live       - the autonomous scheduler/runner loop
"""

__version__ = "0.1.0"
