#!/usr/bin/env python3
"""Run the NASDAQ screener on REAL small/mid-cap data and backtest it.

Universe + metadata: rreichel3/US-Stock-Symbols (marketCap/volume).
Daily adjusted bars: wumiq/us_stock_eod (per-ticker CSV, ~10.8k US stocks incl. small caps).
Both are fetched from raw GitHub and cached to parquet via the existing data layer.

Usage:
    python scripts/screen_nasdaq.py [--limit N] [--start YYYY-MM-DD] [--split YYYY-MM-DD]

Caveats: the bars end 2022-03 (live uses Alpaca) and are symbols-as-of-2022 (partial
survivorship bias). Treat results as evidence the pipeline works, not a proven edge.
"""

from __future__ import annotations

import argparse

from autotrader.backtest.metrics import train_test_split
from autotrader.backtest.runner import run_backtest
from autotrader.data.loader import load_bars, make_eod_fetcher, nasdaq_symbols
from autotrader.strategy.mean_reversion import MeanReversionStrategy
from autotrader.strategy.momentum import MomentumStrategy
from autotrader.strategy.screener import ScreenerStrategy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80, help="universe size (most liquid NASDAQ)")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2022-03-25")
    ap.add_argument("--split", default="2021-01-01", help="train/test cutoff")
    args = ap.parse_args()

    universe = nasdaq_symbols(limit=args.limit)
    print(f"universe: {len(universe)} liquid NASDAQ names; fetching bars (cached after first)...")
    bars = load_bars(universe, args.start, args.end, fetcher=make_eod_fetcher())
    print(f"loaded bars for {len(bars)} symbols\n")

    train, test = train_test_split(bars, args.split)

    def report(label, bset, strat):
        r = run_backtest(bset, strat, starting_cash=10_000, slippage_perc=0.0005)
        print(
            f"  [{label:16s}] trades={r.num_trades:4d}  ret={r.total_return:+8.2%}  "
            f"Sharpe={r.sharpe:5.2f}  Sortino={r.sortino:5.2f}  "
            f"maxDD={r.max_drawdown:6.2%}  win={r.win_rate:4.0%}"
        )

    print("SCREENER (composite, ranked):")
    report("in-sample", train, ScreenerStrategy())
    report("OUT-OF-SAMPLE", test, ScreenerStrategy())
    print("baselines (OOS):")
    report("momentum", test, MomentumStrategy(lookback=20))
    report("mean_reversion", test, MeanReversionStrategy(rsi_period=2, rsi_entry=10))

    # Ranked candidates on the most recent available bar.
    sigs = ScreenerStrategy().generate(bars)
    latest = []
    for sym, lst in sigs.items():
        last_date = bars[sym].index[-1]
        todays = [s for s in lst if s.timestamp == last_date]
        if todays:
            latest.append(todays[-1])
    latest.sort(key=lambda s: s.score, reverse=True)
    print(f"\nTop candidates as of {args.end}:")
    print(f"  {'SYMBOL':8s} {'SCORE':>6s}  {'PATTERN':22s} {'STOP':>9s} {'TARGET':>9s}")
    for s in latest[:15]:
        print(f"  {s.symbol:8s} {s.score:6.2f}  {s.pattern or '':22s} "
              f"{s.stop_loss:9.2f} {s.take_profit:9.2f}")


if __name__ == "__main__":
    main()
