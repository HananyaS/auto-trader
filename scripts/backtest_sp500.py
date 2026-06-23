#!/usr/bin/env python3
"""Reproducible real-data backtest on the S&P 500 (2013-2018).

Downloads a real OHLCV dataset (505 S&P 500 names, daily, 2013-02..2018-02) from a
GitHub-hosted CSV, then runs an out-of-sample backtest of both baseline strategies.

Usage:
    python scripts/backtest_sp500.py [--top N] [--split YYYY-MM-DD]

Caveats (read before trusting the numbers):
- Selecting the "top-N by dollar volume over the whole period" and requiring full
  coverage introduces selection + survivorship bias that flatters results.
- The dataset is split-adjusted but not dividend-adjusted.
- This shows the *pipeline* on real data; it is not a validated edge.
"""

from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

from autotrader.backtest.metrics import buy_and_hold_return, train_test_split
from autotrader.backtest.runner import run_backtest
from autotrader.data.loader import load_csv_bars
from autotrader.strategy.mean_reversion import MeanReversionStrategy
from autotrader.strategy.momentum import MomentumStrategy

DATA_URL = "https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv"
CACHE = Path("data_cache/sp500_5yr.csv")


def ensure_data() -> Path:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading {DATA_URL} ...")
        urllib.request.urlopen(DATA_URL, timeout=120)  # noqa: S310 - fixed trusted URL
        urllib.request.urlretrieve(DATA_URL, CACHE)  # noqa: S310
    return CACHE


def liquid_full_coverage_universe(path: Path, top: int) -> list[str]:
    raw = pd.read_csv(path, parse_dates=["date"])
    full_len = raw.groupby("Name").size().max()
    full = raw.groupby("Name").size()
    full_syms = full[full == full_len].index  # full coverage only
    raw = raw[raw.Name.isin(full_syms)].copy()
    raw["dv"] = raw.close * raw.volume
    return raw.groupby("Name")["dv"].mean().sort_values(ascending=False).head(top).index.tolist()


def report(label: str, bars, strat) -> None:
    r = run_backtest(bars, strat, starting_cash=10_000, slippage_perc=0.0005)
    print(
        f"  [{label:16s}] trades={r.num_trades:4d}  ret={r.total_return:+8.2%}  "
        f"Sharpe={r.sharpe:5.2f}  Sortino={r.sortino:5.2f}  "
        f"maxDD={r.max_drawdown:6.2%}  win={r.win_rate:4.0%}"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=80, help="universe size (most liquid)")
    ap.add_argument("--split", default="2016-02-08", help="train/test cutoff date")
    args = ap.parse_args()

    path = ensure_data()
    universe = liquid_full_coverage_universe(path, args.top)
    bars = load_csv_bars(str(path), symbols=universe)
    print(f"universe: {len(bars)} full-coverage liquid S&P 500 names")

    train, test = train_test_split(bars, args.split)
    print(f"train: ..{args.split} | test (OOS): {args.split}..\n")

    print("MOMENTUM (20d breakout, 2d hold):")
    report("in-sample", train, MomentumStrategy(lookback=20))
    report("OUT-OF-SAMPLE", test, MomentumStrategy(lookback=20))
    print("MEAN-REVERSION (RSI2<10, 2d hold):")
    report("in-sample", train, MeanReversionStrategy(rsi_period=2, rsi_entry=10))
    report("OUT-OF-SAMPLE", test, MeanReversionStrategy(rsi_period=2, rsi_entry=10))

    bh = np.mean([buy_and_hold_return(df["close"]) for df in test.values()])
    print(f"\nbenchmark: equal-weight buy & hold (OOS): {bh:+.2%}")


if __name__ == "__main__":
    main()
