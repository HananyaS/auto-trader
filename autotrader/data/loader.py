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

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pandas as pd

log = logging.getLogger("autotrader.data")

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
    skip_errors: bool = True,
) -> Bars:
    """Return ``{symbol: cleaned OHLCV}`` for the window, caching to parquet.

    On a cache hit that covers the window we read from disk; otherwise we fetch,
    clean, persist, and slice. With ``skip_errors`` (default), a symbol that fails
    to fetch (e.g. a delisted ticker 404) is logged and omitted so one bad ticker
    can't abort a market-wide scan; set False to surface the exception.
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
            try:
                raw = fetch(symbol, start, end, timeframe)
                df = clean_bars(raw)
            except Exception as exc:  # noqa: BLE001 - one bad ticker shouldn't abort
                if not skip_errors:
                    raise
                log.warning("skipping %s: %s", symbol, exc)
                continue
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


# --- NASDAQ universe + a GitHub-hosted EOD fetcher (Screener feature) ----------

# Full NASDAQ listing with metadata (marketCap, volume, sector); current snapshot.
NASDAQ_UNIVERSE_URL = (
    "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/"
    "nasdaq/nasdaq_full_tickers.json"
)


def _http_get(url: str, *, retries: int = 4, timeout: int = 30) -> bytes:
    """Fetch a URL robustly: urllib with retries, then a curl fallback.

    Some proxied environments truncate large responses under urllib (IncompleteRead)
    while curl handles them, so we fall back to curl if available.
    """
    import time
    import urllib.request

    last: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - https
                return resp.read()
        except Exception as exc:  # noqa: BLE001 - retry any transient failure
            last = exc
            time.sleep(min(2**attempt, 8))

    import shutil
    import subprocess

    if shutil.which("curl"):
        out = subprocess.run(  # noqa: S603
            ["curl", "-fsSL", "--max-time", str(timeout), url],  # noqa: S607
            capture_output=True,
            timeout=timeout + 10,
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout
        last = RuntimeError(f"curl exited {out.returncode}: {out.stderr.decode()[:200]}")
    raise RuntimeError(f"failed to fetch {url} after {retries} attempts: {last}")


def nasdaq_universe(*, use_cache: bool = True, cache_dir: Path = DEFAULT_CACHE_DIR) -> pd.DataFrame:
    """Return the NASDAQ universe with metadata, indexed by symbol.

    Columns include ``marketCap`` and ``volume`` (coerced to numeric). Cached to
    parquet. NOTE: this is a *current* snapshot, not point-in-time membership.
    """
    import io

    cache_dir = Path(cache_dir)
    path = cache_dir / "nasdaq_universe.parquet"
    if use_cache and path.exists():
        return pd.read_parquet(path)

    df = pd.read_json(io.BytesIO(_http_get(NASDAQ_UNIVERSE_URL)))
    for col in ("marketCap", "volume", "lastsale"):
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce"
            )
    df = df.set_index("symbol")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def nasdaq_symbols(
    *,
    min_market_cap: float = 3e8,
    min_dollar_volume: float = 1e7,
    exclude_suffixes: tuple[str, ...] = ("W", "U", "R"),
    limit: int | None = None,
    use_cache: bool = True,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[str]:
    """Tradeable NASDAQ tickers: cheap pre-filter before fetching bars.

    Drops tiny caps, illiquid names, and SPAC warrant/unit/right tickers (which
    usually end in W/U/R). Sorted by descending dollar volume so ``limit`` keeps
    the most liquid names.
    """
    df = nasdaq_universe(use_cache=use_cache, cache_dir=cache_dir).copy()
    df["dollar_volume"] = df.get("lastsale", 0) * df.get("volume", 0)
    mask = (df["marketCap"].fillna(0) >= min_market_cap) & (
        df["dollar_volume"].fillna(0) >= min_dollar_volume
    )
    df = df[mask]
    symbols = [s for s in df.sort_values("dollar_volume", ascending=False).index if "$" not in s]
    symbols = [s for s in symbols if not s.endswith(exclude_suffixes)]
    return symbols[:limit] if limit else symbols


# Per-ticker EOD CSVs: <FIRST_LETTER>/<TICKER>.csv with an "Adj Close" column.
EOD_REPO = "wumiq/us_stock_eod"


def make_eod_fetcher(repo: str = EOD_REPO) -> Fetcher:
    """Build a ``Fetcher`` that pulls adjusted daily bars from a GitHub EOD repo.

    The repo stores split/dividend-adjusted CSVs; we map ``Adj Close`` -> ``close``
    so backtests use adjusted prices. Plug into ``load_bars(..., fetcher=...)`` to
    get parquet caching + hygiene for free.
    """
    import io

    base = f"https://raw.githubusercontent.com/{repo}/main"

    def fetch(symbol: str, start: str, end: str, timeframe: str) -> pd.DataFrame:
        url = f"{base}/{symbol[0].upper()}/{symbol.upper()}.csv"
        raw = pd.read_csv(io.BytesIO(_http_get(url)), parse_dates=["Date"]).set_index("Date")
        if "Adj Close" in raw.columns:
            raw = raw.drop(columns=["Close"]).rename(columns={"Adj Close": "Close"})
        raw = raw.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        if raw.empty:
            raise ValueError(f"no data for {symbol} in [{start}..{end}]")
        return raw

    return fetch
