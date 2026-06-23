"""Historical bar loading + local caching.

Phase 2 (see ROADMAP.md). Prototype with yfinance for free daily bars, then
switch to the Alpaca data API. Returns clean, split/dividend-adjusted DataFrames
and caches them locally (parquet) for fast, reproducible backtests.
"""

from __future__ import annotations

import pandas as pd


def load_bars(
    symbols: list[str],
    start: str,
    end: str,
    *,
    timeframe: str = "1d",
    use_cache: bool = True,
) -> dict[str, pd.DataFrame]:
    """Return {symbol: OHLCV DataFrame} for the given window.

    TODO(Phase 2): implement fetch + parquet cache + adjustment/hygiene.
    """
    raise NotImplementedError("Phase 2: implement data loading + caching")


def sp500_symbols() -> list[str]:
    """Return the current S&P 500 constituent tickers (our trading universe).

    TODO(Phase 2): source from a maintained list; mind survivorship bias when
    backtesting (use point-in-time membership if/when available).
    """
    raise NotImplementedError("Phase 2: implement S&P 500 universe loading")
