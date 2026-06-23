"""Tests for the NASDAQ screener: indicators, patterns, scoring, engine, data.

All synthetic / injected — no network.
"""

import numpy as np
import pandas as pd
import pytest

from autotrader.live.runner import _scale_by_score
from autotrader.strategy.indicators import (
    adr_pct,
    atr,
    bollinger,
    ema,
    gap_pct,
    rvol,
    sma,
    true_range,
)
from autotrader.strategy.screener import (
    FiftyTwoWeekBreakout,
    GapFill,
    RSI2MeanReversion,
    ScreenerStrategy,
    VolumeSpikeBreakout,
    composite_score,
)


def _frame(close, *, open_=None, high=None, low=None, volume=1_000):
    idx = pd.date_range("2020-01-01", periods=len(close), freq="B")
    ser = lambda v, default: (  # noqa: E731
        pd.Series(v, index=idx, dtype=float) if v is not None else default
    )
    close = pd.Series(close, index=idx, dtype=float)
    o = ser(open_, close.shift(1).fillna(close))
    hi = ser(high, np.maximum(o, close) * 1.005)
    lo = ser(low, np.minimum(o, close) * 0.995)
    vol = pd.Series(volume, index=idx, dtype=float)
    return pd.DataFrame({"open": o, "high": hi, "low": lo, "close": close, "volume": vol})


# --- indicators ---------------------------------------------------------------


def test_sma_and_ema_basic():
    s = pd.Series(np.arange(1, 11), dtype=float)
    assert sma(s, 2).iloc[-1] == pytest.approx(9.5)
    assert np.isfinite(ema(s, 3).iloc[-1])
    with pytest.raises(ValueError):
        sma(s, 0)


def test_true_range_and_atr_positive():
    df = _frame(list(np.linspace(100, 110, 30)))
    tr = true_range(df)
    assert (tr.dropna() >= 0).all()
    a = atr(df, 14).dropna()
    assert (a > 0).all()


def test_bollinger_bands_ordered():
    df = _frame(list(np.linspace(100, 120, 40)))
    lower, mid, upper = bollinger(df["close"], 20, 2.0)
    last = -1
    assert lower.iloc[last] <= mid.iloc[last] <= upper.iloc[last]
    assert mid.iloc[last] == pytest.approx(sma(df["close"], 20).iloc[last])


def test_rvol_spikes_and_excludes_today():
    vol = [1000] * 25 + [5000]  # last bar 5x the baseline
    df = _frame([100.0] * 26, volume=vol)
    r = rvol(df["volume"], 20)
    assert r.iloc[-1] == pytest.approx(5.0, rel=0.01)


def test_gap_pct_sign_and_adr_nonneg():
    df = _frame([100, 100, 100, 100], open_=[100, 100, 95, 100])
    assert gap_pct(df).iloc[2] == pytest.approx(-0.05)  # gap down
    assert (adr_pct(_frame(list(np.linspace(100, 110, 30))), 20).dropna() >= 0).all()


# --- patterns -----------------------------------------------------------------


def test_rsi2_fires_in_uptrend_dip_and_silent_in_downtrend():
    a_up = _frame(list(np.linspace(100, 180, 205)) + [175, 170, 165])
    res = RSI2MeanReversion()(a_up, atr(a_up, 14))
    assert res.raw.iloc[-1] > 0  # oversold above SMA200 -> fires
    assert res.stop.iloc[-1] < a_up["close"].iloc[-1] < res.target.iloc[-1]

    down = _frame(list(np.linspace(180, 100, 205)) + [98, 96, 94])
    assert RSI2MeanReversion()(down, atr(down, 14)).raw.iloc[-1] == 0  # below SMA200


def test_52week_breakout_requires_volume():
    base = [100.0] * 255
    hi, lo = [100.2] * 255 + [110.2], [99.8] * 256
    fire = _frame(base + [110.0], volume=[1000] * 255 + [12000], high=hi, low=lo)
    assert FiftyTwoWeekBreakout()(fire, atr(fire, 14)).raw.iloc[-1] > 0

    no_vol = _frame(base + [110.0], volume=[1000] * 256, high=hi, low=lo)
    assert FiftyTwoWeekBreakout()(no_vol, atr(no_vol, 14)).raw.iloc[-1] == 0


def test_volume_spike_breakout_fires():
    df = _frame(
        [100.0] * 25 + [105.0],
        open_=[100.0] * 25 + [100.5],
        volume=[1000] * 25 + [8000],
    )
    res = VolumeSpikeBreakout()(df, atr(df, 14))
    assert res.raw.iloc[-1] > 0
    assert res.stop.iloc[-1] < df["close"].iloc[-1]


def test_gap_fill_fires_on_gap_down_recovery():
    close = [100.0] * 20 + [98.0]   # prev close 100; today closes 98 (< prev, > open)
    open_ = [100.0] * 20 + [95.0]   # gap down 5%
    df = _frame(close, open_=open_, low=[99.0] * 20 + [94.5])
    res = GapFill()(df, atr(df, 14))
    assert res.raw.iloc[-1] > 0
    assert res.target.iloc[-1] == pytest.approx(100.0)  # target == prior close (the fill)


# --- composite scoring --------------------------------------------------------


def test_composite_confluence_beats_single():
    idx = pd.date_range("2020-01-01", periods=1, freq="B")
    weights = pd.Series({"p1": 1.0, "p2": 1.0})
    one = pd.DataFrame({"p1": [0.5], "p2": [0.0]}, index=idx)
    two = pd.DataFrame({"p1": [0.5], "p2": [0.5]}, index=idx)
    assert composite_score(two, weights).iloc[0] > composite_score(one, weights).iloc[0]
    assert composite_score(two, weights).iloc[0] <= 1.0


def test_composite_zero_when_nothing_fires():
    idx = pd.date_range("2020-01-01", periods=1, freq="B")
    raw = pd.DataFrame({"p1": [0.0]}, index=idx)
    assert composite_score(raw, pd.Series({"p1": 1.0})).fillna(0).iloc[0] == 0.0


# --- ScreenerStrategy ---------------------------------------------------------


def _breakout_frame():
    base = [100.0] * 255
    return _frame(
        base + [110.0],
        open_=base + [100.5],
        high=[100.2] * 255 + [110.5],
        low=[99.8] * 256,
        volume=[200_000] * 255 + [2_000_000],
    )


def test_screener_emits_scored_signal():
    bars = {"AAA": _breakout_frame()}
    sigs = ScreenerStrategy().generate(bars)
    assert "AAA" in sigs
    last = sigs["AAA"][-1]
    assert 0.0 < last.score <= 1.0
    assert last.pattern
    assert last.stop_loss < 110.0 < last.take_profit
    assert last.max_hold_days <= 2


def test_screener_liquidity_gate_skips_thin_names():
    # Same breakout but tiny dollar volume -> filtered out.
    base = [100.0] * 255
    thin = _frame(base + [110.0], high=[100.2] * 255 + [110.5], low=[99.8] * 256, volume=[10] * 256)
    assert "X" not in ScreenerStrategy(min_dollar_volume=1e7).generate({"X": thin})


def test_screener_is_pure_no_mutation():
    bars = {"AAA": _breakout_frame()}
    snapshot = bars["AAA"].copy()
    ScreenerStrategy().generate(bars)
    pd.testing.assert_frame_equal(bars["AAA"], snapshot)


# --- engine: score-scaled sizing ----------------------------------------------


def test_scale_by_score_reduces_and_preserves_legacy():
    assert _scale_by_score(100, 0.0) == 100          # legacy unscored -> unchanged
    assert _scale_by_score(100, 1.0) == 100          # full conviction -> full size
    assert _scale_by_score(100, 0.5) == 75           # floor 0.5 + 0.5*0.5
    assert _scale_by_score(100, 0.0001) < 100        # low conviction shrinks


# --- engine: ranking by score -------------------------------------------------


def test_place_entries_fills_highest_score_first():
    from autotrader.config import RiskLimits
    from autotrader.execution.sim import SimBroker
    from autotrader.live.runner import TradingEngine
    from autotrader.strategy.base import Side, Signal

    df = _frame([100.0] * 10)
    bars = {"LO": df, "HI": df}

    class _Fake:
        name = "fake"

        def generate(self, _bars):
            mk = lambda sym, score: Signal(  # noqa: E731
                sym, df.index[-1], Side.BUY, stop_loss=95.0, take_profit=110.0, score=score
            )
            return {"LO": [mk("LO", 0.3)], "HI": [mk("HI", 0.9)]}

    broker = SimBroker(cash=10_000)
    broker.set_price("LO", 100.0)
    broker.set_price("HI", 100.0)
    engine = TradingEngine(
        broker, _Fake(), bar_loader=lambda: bars, limits=RiskLimits(max_concurrent_positions=1)
    )
    engine.run_once()

    held = [p.symbol for p in broker.get_positions()]
    assert held == ["HI"]  # only one slot -> highest score wins


# --- data: NASDAQ universe filter + EOD fetcher -------------------------------


def test_nasdaq_symbols_filters(monkeypatch):
    from autotrader.data import loader

    uni = pd.DataFrame(
        {
            "marketCap": [5e9, 1e8, 5e9, 5e9],   # BIG ok, TINY too small
            "volume": [1e6, 1e6, 1e6, 1e6],
            "lastsale": [50, 50, 50, 50],
        },
        index=["BIG", "TINY", "GOODW", "OK"],
    )
    monkeypatch.setattr(loader, "nasdaq_universe", lambda **k: uni)
    syms = loader.nasdaq_symbols(min_market_cap=3e8, min_dollar_volume=1e6)
    assert "BIG" in syms and "OK" in syms
    assert "TINY" not in syms      # below market-cap floor
    assert "GOODW" not in syms     # warrant suffix 'W' excluded


def test_make_eod_fetcher_maps_adj_close(monkeypatch):
    from autotrader.data import loader

    csv = (
        b"Date,Open,High,Low,Close,Adj Close,Volume\n"
        b"2021-01-04,10,10,9,10,5,100\n"
        b"2021-01-05,11,11,10,11,6,200\n"
    )
    monkeypatch.setattr(loader, "_http_get", lambda url, **k: csv)  # no network
    fetch = loader.make_eod_fetcher()
    out = fetch("AAPL", "2021-01-01", "2021-12-31", "1d")
    # Adj Close should have replaced Close (adjusted prices used downstream).
    assert list(out["Close"]) == [5, 6]
    assert "Adj Close" not in out.columns
