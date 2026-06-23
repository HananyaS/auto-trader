#!/usr/bin/env python3
"""Fair, edge-aware evaluation of every strategy on REAL NASDAQ data.

For each strategy (7 screener patterns individually, the composite screener, momentum,
mean-reversion) it reports, out-of-sample and after costs:
- exposure + return-on-exposure (undoes the cash-drag that makes B&H look better),
- Sharpe / Sortino, expectancy, profit factor,
- significance: t-stat + bootstrap CI on per-trade returns,
- EDGE: percentile vs a random-entry null matched on trade count + holding,
- walk-forward aggregate across rolling OOS windows, with bull/bear regime tags,
- index buy & hold (SPY) over the same window.

Usage: python scripts/evaluate_strategies.py [--limit N] [--split YYYY-MM-DD] [--runs N]
Caveats: bars end 2022 and are symbols-as-of-2022 (survivorship); liquidity-selected universe.
"""

from __future__ import annotations

import argparse

from autotrader.backtest.evaluate import (
    dominant_regime,
    mean_metric,
    random_entry_benchmark,
    single_pattern_strategy,
    walk_forward,
)
from autotrader.backtest.metrics import (
    bootstrap_ci,
    buy_and_hold_return,
    percentile_rank,
    t_stat,
    train_test_split,
)
from autotrader.backtest.runner import run_backtest
from autotrader.data.loader import load_bars, make_eod_fetcher, nasdaq_symbols
from autotrader.strategy.mean_reversion import MeanReversionStrategy
from autotrader.strategy.momentum import MomentumStrategy
from autotrader.strategy.screener import ScreenerStrategy, default_patterns


def _strategies():
    out = {p.name: single_pattern_strategy(p) for p in default_patterns()}
    out["SCREENER(composite)"] = ScreenerStrategy()
    out["momentum"] = MomentumStrategy(lookback=20)
    out["mean_reversion"] = MeanReversionStrategy(rsi_period=2, rsi_entry=10)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2022-03-25")
    ap.add_argument("--split", default="2021-01-01")
    ap.add_argument("--runs", type=int, default=100, help="random-null Monte-Carlo runs")
    args = ap.parse_args()

    fetcher = make_eod_fetcher()
    universe = nasdaq_symbols(limit=args.limit)
    print(f"fetching {len(universe)} NASDAQ names + SPY (cached after first run)...")
    bars = load_bars(universe, args.start, args.end, fetcher=fetcher)
    spy = load_bars(["SPY"], args.start, args.end, fetcher=fetcher).get("SPY")
    spy_close = spy["close"] if spy is not None else None
    print(f"loaded {len(bars)} symbols\n")

    _, test = train_test_split(bars, args.split)
    t0 = min(d.index[0] for d in test.values())
    t1 = max(d.index[-1] for d in test.values())
    regime = dominant_regime(spy_close, t0, t1) if spy_close is not None else "n/a"
    print(f"OOS window {t0.date()}..{t1.date()}  (regime: {regime})")
    if spy_close is not None:
        bh = buy_and_hold_return(spy_close.loc[t0:t1])
        print(f"index benchmark  SPY buy & hold (OOS): {bh:+.2%}")
    print()

    cols = ("STRATEGY", "ret", "ret/exp", "exp", "Shrp", "PF", "trades", "tstat", "edge%")
    header = f"{cols[0]:22s}{cols[1]:>8s}{cols[2]:>9s}{cols[3]:>6s}{cols[4]:>6s}" + \
        f"{cols[5]:>6s}{cols[6]:>7s}{cols[7]:>7s}{cols[8]:>7s}"
    print(header)
    print("-" * len(header))

    for name, strat in _strategies().items():
        r = run_backtest(test, strat, starting_cash=10_000, slippage_perc=0.0005)
        if r.num_trades == 0:
            print(f"{name:22s}{'(no trades)':>20s}")
            continue
        null = random_entry_benchmark(
            test, n_trades=r.num_trades, hold_days=2, n_runs=args.runs, slippage_perc=0.0005
        )
        edge = percentile_rank(r.total_return, [x.total_return for x in null])
        lo, hi = bootstrap_ci(r.trade_returns)
        sig = "*" if lo > 0 or hi < 0 else " "  # CI excludes 0
        print(
            f"{name:22s}{r.total_return:+8.1%}{r.return_on_exposure:+9.1%}{r.exposure:6.0%}"
            f"{r.sharpe:6.2f}{r.profit_factor:6.2f}{r.num_trades:7d}"
            f"{t_stat(r.trade_returns):7.2f}{edge:6.0%}{sig}"
        )

    # Walk-forward robustness for the composite screener.
    print("\nWalk-forward (composite screener), per OOS fold:")
    folds = walk_forward(bars, lambda _t: ScreenerStrategy(), n_splits=4, slippage_perc=0.0005)
    for start, end, res in folds:
        reg = dominant_regime(spy_close, start, end) if spy_close is not None else "n/a"
        print(f"  {start.date()}..{end.date()} [{reg:4s}]  ret={res.total_return:+7.1%}  "
              f"Sharpe={res.sharpe:5.2f}  ret/exp={res.return_on_exposure:+7.1%}  "
              f"trades={res.num_trades}")
    if folds:
        print(f"  aggregate: mean ret={mean_metric([f[2] for f in folds],'total_return'):+.1%}  "
              f"mean Sharpe={mean_metric([f[2] for f in folds],'sharpe'):.2f}")

    print("\nReading: 'edge%' = percentile vs random-entry null (>50% beats luck on average; "
          ">95% is a real signal). '*' = per-trade CI excludes 0. 'ret/exp' undoes cash drag.")


if __name__ == "__main__":
    main()
