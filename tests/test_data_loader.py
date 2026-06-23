"""Tests for the market-data layer (Phase 2).

These exercise the pure hygiene logic and the cache orchestration with an
injected fetcher, so no network access is required.
"""

import numpy as np
import pandas as pd
import pytest

from autotrader.data.loader import clean_bars, load_bars, load_csv_bars


def _raw_frame(dates, *, messy=False):
    """Build a yfinance-style raw frame (mixed-case cols, optional warts)."""
    df = pd.DataFrame(
        {
            "Open": np.arange(len(dates), dtype=float),
            "High": np.arange(len(dates), dtype=float) + 1,
            "Low": np.arange(len(dates), dtype=float) - 1,
            "Close": np.arange(len(dates), dtype=float) + 0.5,
            "Volume": np.arange(len(dates)) * 100,
        },
        index=pd.DatetimeIndex(dates),
    )
    if messy:
        df = df.iloc[::-1]  # unsorted
        df.loc[df.index[0], "Close"] = np.nan  # a NaN OHLC row to be dropped
    return df


def test_clean_bars_standardizes_schema():
    raw = _raw_frame(pd.date_range("2024-01-01", periods=5), messy=True)
    cleaned = clean_bars(raw)

    assert list(cleaned.columns) == ["open", "high", "low", "close", "volume"]
    assert cleaned.index.name == "date"
    assert cleaned.index.is_monotonic_increasing
    assert cleaned.index.tz is None
    # the injected NaN-close row is dropped
    assert cleaned["close"].notna().all()
    assert len(cleaned) == 4


def test_clean_bars_flattens_multiindex_columns():
    dates = pd.date_range("2024-01-01", periods=3)
    raw = _raw_frame(dates)
    raw.columns = pd.MultiIndex.from_product([raw.columns, ["AAPL"]])
    cleaned = clean_bars(raw)
    assert list(cleaned.columns) == ["open", "high", "low", "close", "volume"]


def test_clean_bars_raises_on_missing_columns():
    raw = pd.DataFrame({"Open": [1.0], "Close": [1.0]}, index=pd.to_datetime(["2024-01-01"]))
    with pytest.raises(ValueError, match="missing required columns"):
        clean_bars(raw)


def test_load_bars_fetches_then_caches(tmp_path):
    dates = pd.date_range("2024-01-01", periods=10)
    calls = {"n": 0}

    def fake_fetcher(symbol, start, end, timeframe):
        calls["n"] += 1
        return _raw_frame(dates)

    first = load_bars(
        ["AAPL"], "2024-01-01", "2024-01-10", cache_dir=tmp_path, fetcher=fake_fetcher
    )
    assert calls["n"] == 1
    assert "AAPL" in first
    assert (tmp_path / "AAPL_1d.parquet").exists()

    # Second call is served from cache -> fetcher must NOT be invoked again.
    def exploding_fetcher(*a, **k):
        raise AssertionError("fetcher should not be called on a cache hit")

    second = load_bars(
        ["AAPL"], "2024-01-01", "2024-01-10", cache_dir=tmp_path, fetcher=exploding_fetcher
    )
    # check_freq=False: parquet round-trip drops the index freq attribute, not data.
    pd.testing.assert_frame_equal(first["AAPL"], second["AAPL"], check_freq=False)


def test_load_bars_refetches_when_cache_does_not_cover_window(tmp_path):
    short = pd.date_range("2024-01-01", periods=3)
    wide = pd.date_range("2024-01-01", periods=20)
    seq = iter([_raw_frame(short), _raw_frame(wide)])

    def fetcher(symbol, start, end, timeframe):
        return next(seq)

    # Prime cache with a narrow window.
    load_bars(["MSFT"], "2024-01-01", "2024-01-03", cache_dir=tmp_path, fetcher=fetcher)
    # Asking for a wider window the cache can't cover triggers a refetch.
    result = load_bars(["MSFT"], "2024-01-01", "2024-01-20", cache_dir=tmp_path, fetcher=fetcher)
    assert result["MSFT"].index.max() >= pd.Timestamp("2024-01-19")


def test_load_bars_slices_to_requested_window(tmp_path):
    dates = pd.date_range("2024-01-01", periods=30)

    def fetcher(symbol, start, end, timeframe):
        return _raw_frame(dates)

    result = load_bars(
        ["SPY"], "2024-01-05", "2024-01-10", cache_dir=tmp_path, fetcher=fetcher
    )
    bars = result["SPY"]
    assert bars.index.min() >= pd.Timestamp("2024-01-05")
    assert bars.index.max() <= pd.Timestamp("2024-01-10")


def test_load_csv_bars_long_format(tmp_path):
    # long-format CSV: date, OHLCV, symbol per row (two symbols, one too short)
    rows = []
    for d in pd.date_range("2024-01-01", periods=5):
        rows.append([d, 10, 11, 9, 10, 100, "AAA"])
    rows.append([pd.Timestamp("2024-01-01"), 10, 11, 9, 10, 100, "TINY"])  # 1 bar
    csv = tmp_path / "prices.csv"
    pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "Name"]).to_csv(
        csv, index=False
    )

    bars = load_csv_bars(str(csv), min_bars=2)
    assert set(bars) == {"AAA"}  # TINY dropped for being too short
    assert list(bars["AAA"].columns) == ["open", "high", "low", "close", "volume"]
    assert len(bars["AAA"]) == 5


def test_load_csv_bars_symbol_and_date_filter(tmp_path):
    rows = []
    for sym in ("AAA", "BBB"):
        for d in pd.date_range("2024-01-01", periods=10):
            rows.append([d, 10, 11, 9, 10, 100, sym])
    csv = tmp_path / "prices.csv"
    pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "Name"]).to_csv(
        csv, index=False
    )

    bars = load_csv_bars(str(csv), symbols=["AAA"], start="2024-01-03", end="2024-01-06")
    assert set(bars) == {"AAA"}
    assert bars["AAA"].index.min() == pd.Timestamp("2024-01-03")
    assert bars["AAA"].index.max() == pd.Timestamp("2024-01-06")
