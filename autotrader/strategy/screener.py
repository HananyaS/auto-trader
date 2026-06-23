"""NASDAQ multi-pattern screener (see plan).

Scans a large universe each day across several daily-bar patterns in two buckets —
slower/high-confidence (mean-reversion) and faster/high-tempo (breakouts) — then
ranks candidates with a composite score. Patterns are **vectorized over full
history** (like ``MomentumStrategy``/``MeanReversionStrategy``), so one
implementation serves both ``run_backtest`` (replays all dates) and the live
``TradingEngine`` (acts on the latest bar).

``ScreenerStrategy`` satisfies the ``Strategy`` protocol: ``generate(bars) -> SignalSet``,
pure and side-effect free. Emitted ``Signal``s carry a composite ``score`` in [0, 1]
and the dominant ``pattern`` name for ranking + score-scaled sizing in the engine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from autotrader.strategy.base import Side, Signal, SignalSet
from autotrader.strategy.indicators import (
    atr,
    bollinger,
    gap_pct,
    prior_rolling_high,
    rsi,
    rvol,
    sma,
)


@dataclass(frozen=True)
class PatternResult:
    """Per-date vectorized output of one pattern over a symbol's history."""

    raw: pd.Series  # strength in [0, 1]; 0.0 == no fire on that date
    stop: pd.Series  # stop price per date
    target: pd.Series  # target price per date


# A pattern maps (df, atr_series) -> PatternResult. Implemented as small classes
# carrying sweepable params, each exposing ``name`` and ``max_hold``.
PatternFn = Callable[[pd.DataFrame, pd.Series], PatternResult]


def _fire(raw: pd.Series, fired: pd.Series) -> pd.Series:
    return raw.where(fired, 0.0).fillna(0.0).clip(0.0, 1.0)


# --- BUCKET 1: slower / higher-confidence (mean-reversion) --------------------


class RSI2MeanReversion:
    name = "rsi2_mean_reversion"
    max_hold = 2

    def __init__(self, rsi_period=2, rsi_entry=10.0, trend=200, stop_mult=1.5, target_mult=2.5):
        self.rsi_period, self.rsi_entry, self.trend = rsi_period, rsi_entry, trend
        self.stop_mult, self.target_mult = stop_mult, target_mult

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c = df["close"]
        r = rsi(c, self.rsi_period)
        fired = (r < self.rsi_entry) & (c > sma(c, self.trend))
        raw = _fire((self.rsi_entry - r) / self.rsi_entry, fired)
        return PatternResult(raw, c - self.stop_mult * a, c + self.target_mult * a)


class PullbackTo20MA:
    name = "pullback_20ma"
    max_hold = 2

    def __init__(self, ma=20, trend=50, rsi_floor=40.0, stop_mult=1.5, target_mult=2.5):
        self.ma, self.trend, self.rsi_floor = ma, trend, rsi_floor
        self.stop_mult, self.target_mult = stop_mult, target_mult

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c, low = df["close"], df["low"]
        ma, trend = sma(c, self.ma), sma(c, self.trend)
        fired = (ma > trend) & (low <= ma) & (c >= ma) & (rsi(c, 14) > self.rsi_floor)
        raw = _fire(1.0 - ((low - ma).abs() / (0.5 * a)), fired)
        stop = np.minimum(trend, c - self.stop_mult * a)
        return PatternResult(raw, stop, c + self.target_mult * a)


class BollingerReversion:
    name = "bollinger_reversion"
    max_hold = 2

    def __init__(self, period=20, num_std=2.0, trend=200):
        self.period, self.num_std, self.trend = period, num_std, trend

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c, low = df["close"], df["low"]
        lower, mid, upper = bollinger(c, self.period, self.num_std)
        fired = (low < lower) & (c > lower) & (c > sma(c, self.trend))
        raw = _fire((mid - c) / ((upper - lower) / 2.0), fired)
        return PatternResult(raw, low - 0.25 * a, mid)


class ThreeBarReversal:
    name = "three_bar_reversal"
    max_hold = 2

    def __init__(self, target_mult=2.0):
        self.target_mult = target_mult

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c, o, low, high, vol = df["close"], df["open"], df["low"], df["high"], df["volume"]
        lower_lows = (low.shift(1) < low.shift(2)) & (low.shift(2) < low.shift(3))
        fired = lower_lows & (c > high.shift(1)) & (vol > vol.shift(1))
        raw = _fire((c - o) / a, fired)
        stop = low.rolling(2).min() - 0.1 * a
        return PatternResult(raw, stop, c + self.target_mult * a)


# --- BUCKET 2: faster / higher-tempo (breakouts / momentum) -------------------


class FiftyTwoWeekBreakout:
    name = "fiftytwo_week_breakout"
    max_hold = 2

    def __init__(self, window=252, rvol_min=1.5, vol_period=20, stop_mult=1.5, target_mult=2.5):
        self.window, self.rvol_min, self.vol_period = window, rvol_min, vol_period
        self.stop_mult, self.target_mult = stop_mult, target_mult

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c = df["close"]
        hi = prior_rolling_high(c, self.window)
        rv = rvol(df["volume"], self.vol_period)
        fired = (c > hi) & (rv >= self.rvol_min)
        raw = _fire(
            0.5 * ((rv - self.rvol_min) / 2.0).clip(0, 1) + 0.5 * ((c - hi) / a).clip(0, 1),
            fired,
        )
        return PatternResult(raw, c - self.stop_mult * a, c + self.target_mult * a)


class VolumeSpikeBreakout:
    name = "volume_spike_breakout"
    max_hold = 1

    def __init__(self, window=20, rvol_min=2.0, vol_period=20, stop_mult=1.5, target_mult=2.0):
        self.window, self.rvol_min, self.vol_period = window, rvol_min, vol_period
        self.stop_mult, self.target_mult = stop_mult, target_mult

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c, o = df["close"], df["open"]
        hi = prior_rolling_high(c, self.window)
        rv = rvol(df["volume"], self.vol_period)
        fired = (c > hi) & (rv >= self.rvol_min) & (c > o)
        raw = _fire((rv - self.rvol_min) / 3.0, fired)
        return PatternResult(raw, c - self.stop_mult * a, c + self.target_mult * a)


class GapFill:
    """Long the recovery of a gap-DOWN back toward the prior close (fill)."""

    name = "gap_fill"
    max_hold = 1

    def __init__(self, min_gap=0.02):
        self.min_gap = min_gap

    def __call__(self, df: pd.DataFrame, a: pd.Series) -> PatternResult:
        c, o, low = df["close"], df["open"], df["low"]
        prev_close = c.shift(1)
        g = gap_pct(df)
        fired = (g <= -self.min_gap) & (c > o) & (c < prev_close)
        raw = _fire((-g) / 0.05, fired)
        return PatternResult(raw, low - 0.25 * a, prev_close)


def default_patterns() -> list[PatternFn]:
    return [
        RSI2MeanReversion(),
        PullbackTo20MA(),
        BollingerReversion(),
        ThreeBarReversal(),
        FiftyTwoWeekBreakout(),
        VolumeSpikeBreakout(),
        GapFill(),
    ]


DEFAULT_WEIGHTS: dict[str, float] = {
    "fiftytwo_week_breakout": 1.3,
    "volume_spike_breakout": 1.2,
    "pullback_20ma": 1.1,
    "bollinger_reversion": 1.0,
    "rsi2_mean_reversion": 0.9,
    "three_bar_reversal": 0.8,
    "gap_fill": 0.7,
}


def composite_score(
    raw: pd.DataFrame, weights: pd.Series, confluence_bonus: float = 0.15
) -> pd.Series:
    """Blend per-pattern raw scores into a composite in [0, 1] per date.

    ``base`` is the weight-normalized mean strength of *fired* patterns; a
    ``confluence_bonus`` rewards multiple patterns agreeing on the same date.
    """
    fired = raw > 0
    n_fired = fired.sum(axis=1)
    wsum = fired.mul(weights, axis=1).sum(axis=1)
    weighted = raw.mul(weights, axis=1).sum(axis=1)
    base = weighted / wsum.replace(0, np.nan)
    return (base * (1.0 + confluence_bonus * (n_fired - 1))).clip(0.0, 1.0)


class ScreenerStrategy:
    """Composite multi-pattern screener with ranked, scored signals."""

    name = "screener"

    def __init__(
        self,
        patterns: list[PatternFn] | None = None,
        weights: dict[str, float] | None = None,
        *,
        min_score: float = 0.35,
        min_dollar_volume: float = 1e7,
        max_atr_pct: float = 0.12,
        confluence_bonus: float = 0.15,
        atr_period: int = 14,
    ) -> None:
        self.patterns = patterns if patterns is not None else default_patterns()
        self.weights = weights if weights is not None else DEFAULT_WEIGHTS
        self.min_score = min_score
        self.min_dollar_volume = min_dollar_volume
        self.max_atr_pct = max_atr_pct
        self.confluence_bonus = confluence_bonus
        self.atr_period = atr_period

    def generate(self, bars: dict[str, pd.DataFrame]) -> SignalSet:
        out: SignalSet = {}
        for symbol, df in bars.items():
            sigs = self._scan_symbol(symbol, df)
            if sigs:
                out[symbol] = sigs
        return out

    def _scan_symbol(self, symbol: str, df: pd.DataFrame) -> list[Signal]:
        if len(df) < 60:  # need history for the longer lookbacks
            return []
        c = df["close"]
        a = atr(df, self.atr_period)

        # Per-date tradeability gates (applied as a mask so backtests are honest).
        dollar_vol = (c * df["volume"]).rolling(20).mean()
        atr_pct = a / c
        gate = (dollar_vol >= self.min_dollar_volume) & (atr_pct <= self.max_atr_pct)

        names, raw_cols, stop_cols, tgt_cols, holds = [], {}, {}, {}, {}
        for pat in self.patterns:
            res = pat(df, a)
            names.append(pat.name)
            raw_cols[pat.name] = res.raw
            stop_cols[pat.name] = res.stop.where(res.raw > 0)
            tgt_cols[pat.name] = res.target.where(res.raw > 0)
            holds[pat.name] = pat.max_hold

        raw = pd.DataFrame(raw_cols)
        w = pd.Series({n: self.weights.get(n, 1.0) for n in names})
        fired = raw > 0
        score = composite_score(raw, w, self.confluence_bonus)
        score = score.where(gate, 0.0).fillna(0.0)

        dominant = raw.mul(w, axis=1).idxmax(axis=1)
        stop_agg = pd.DataFrame(stop_cols).max(axis=1)  # tightest stop among fired
        tgt_agg = pd.DataFrame(tgt_cols).min(axis=1)  # nearest target among fired
        hold_df = pd.DataFrame(
            {n: pd.Series(holds[n], index=df.index).where(fired[n]) for n in names}
        )
        hold_agg = hold_df.min(axis=1)

        emit = (score >= self.min_score) & (stop_agg < c) & (tgt_agg > c)
        signals: list[Signal] = []
        for ts in df.index[emit.fillna(False)]:
            signals.append(
                Signal(
                    symbol=symbol,
                    timestamp=ts,
                    side=Side.BUY,
                    stop_loss=float(stop_agg.loc[ts]),
                    take_profit=float(tgt_agg.loc[ts]),
                    max_hold_days=int(hold_agg.loc[ts]),
                    score=float(score.loc[ts]),
                    pattern=str(dominant.loc[ts]),
                )
            )
        return signals
