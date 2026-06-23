"""Historical bar loading + local caching (Phase 2, see ROADMAP.md).

Prototype with yfinance for free, split/dividend-adjusted daily bars; the same
interface will later back onto the Alpaca data API. Bars are cleaned to a
standard schema and cached to parquet for fast, reproducible backtests.

Design notes:
- ``clean_bars`` is a pure function (no I/O) so it is trivially testable.
- ``load_bars`` takes an injectable ``fetcher`` so the orchestration/caching
  logic can be tested without any network access.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pandas as pd

# Standardized OHLCV schema every consumer (strategy, backtest) can rely on.
OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
INDEX_NAME = "date"

# Cached parquet lands here (gitignored). Override per-call for tests.
DEFAULT_CACHE_DIR = Path("data_cache")

# {symbol: cleaned OHLCV DataFrame indexed by date}
Bars = dict[str, pd.DataFrame]


class Fetcher(Protocol):
    """Source of raw bars for one symbol over [start, end]."""

    def __call__(self, symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame: ...


def clean_bars(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize raw vendor bars to the standard OHLCV schema.

    Lower-cases columns, keeps OHLCV, enforces a sorted, de-duplicated,
    tz-naive ``DatetimeIndex`` named ``date``, and drops rows missing any
    OHLC value. Pure: no I/O, no global state.
    """
    df = raw.copy()

    # yfinance can return a MultiIndex (field, ticker) for single-symbol pulls.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]

    # When fetched with auto_adjust=True there is no separate adj_close; close
    # is already split/dividend adjusted. Tolerate either shape.
    missing = [c for c in OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"raw bars missing required columns: {missing}")
    df = df[OHLCV_COLUMNS]

    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df.index.name = INDEX_NAME

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df


def _cache_path(symbol: str, timeframe: str, cache_dir: Path) -> Path:
    return cache_dir / f"{symbol.upper()}_{timeframe}.parquet"


def _covers(df: pd.DataFrame, start: str, end: str) -> bool:
    """True if the cached frame spans the requested window."""
    if df.empty:
        return False
    return df.index.min() <= pd.Timestamp(start) and df.index.max() >= pd.Timestamp(end)


def _fetch_yfinance(symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame:
    """Default fetcher: split/dividend-adjusted bars from yfinance."""
    import yfinance as yf  # imported lazily so the module loads without the dep

    interval = {"1d": "1d", "1h": "60m"}.get(timeframe, timeframe)
    df = yf.download(
        symbol,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=True,
        progress=False,
    )
    if df is None or df.empty:
        raise ValueError(f"no data returned for {symbol} [{start}..{end}]")
    return df


def load_bars(
    symbols: list[str],
    start: str,
    end: str,
    *,
    timeframe: str = "1d",
    use_cache: bool = True,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    fetcher: Fetcher | Callable[..., pd.DataFrame] | None = None,
) -> Bars:
    """Return ``{symbol: cleaned OHLCV}`` for the window, caching to parquet.

    On a cache hit that covers the window we read from disk; otherwise we fetch,
    clean, persist, and slice. Symbols that fail to load are skipped (logged via
    the returned dict simply omitting them) so one bad ticker can't abort a run.
    """
    fetch = fetcher or _fetch_yfinance
    cache_dir = Path(cache_dir)
    out: Bars = {}

    for symbol in symbols:
        path = _cache_path(symbol, timeframe, cache_dir)
        df: pd.DataFrame | None = None

        if use_cache and path.exists():
            cached = pd.read_parquet(path)
            if _covers(cached, start, end):
                df = cached

        if df is None:
            raw = fetch(symbol, start, end, timeframe)
            df = clean_bars(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path)

        window = df.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        if not window.empty:
            out[symbol] = window

    return out


def sp500_symbols(*, use_cache: bool = True, cache_dir: Path = DEFAULT_CACHE_DIR) -> list[str]:
    """Return current S&P 500 constituent tickers (our trading universe).

    Sourced from Wikipedia and cached locally. NOTE: this is the *current*
    membership — backtests over long windows have survivorship bias. Swap in a
    point-in-time constituent source before trusting long-horizon results.
    """
    cache_dir = Path(cache_dir)
    path = cache_dir / "sp500_symbols.parquet"

    if use_cache and path.exists():
        return pd.read_parquet(path)["symbol"].tolist()

    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)  # requires lxml + network
    symbols = tables[0]["Symbol"].astype(str).str.replace(".", "-", regex=False).tolist()

    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"symbol": symbols}).to_parquet(path)
    return symbols


def load_csv_bars(
    path: str,
    *,
    symbol_col: str = "Name",
    date_col: str = "date",
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    min_bars: int = 2,
) -> Bars:
    """Load ``Bars`` from a long-format OHLCV CSV (date, OHLCV, symbol per row).

    Handy for offline backtests on a bundled dataset. Each symbol is cleaned via
    ``clean_bars`` and short/empty series are dropped (``min_bars``), which also
    avoids the backtrader "empty feed halts the run" gotcha.
    """
    raw = pd.read_csv(path, parse_dates=[date_col])
    if symbols is not None:
        raw = raw[raw[symbol_col].isin(symbols)]

    out: Bars = {}
    for symbol, group in raw.groupby(symbol_col):
        df = clean_bars(group.set_index(date_col))
        if start is not None or end is not None:
            df = df.loc[pd.Timestamp(start) if start else None : pd.Timestamp(end) if end else None]
        if len(df) >= min_bars:
            out[str(symbol)] = df
    return out
