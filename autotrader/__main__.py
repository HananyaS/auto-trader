"""Command-line entry point: ``python -m autotrader <command>``.

Commands:
    backtest  - run a strategy over historical bars and print metrics
    run       - one live/paper trading pass right now (or --schedule to loop)
    flatten   - manually close all open positions (safety override)

``build_parser`` is separated out so argument parsing is unit-testable without
touching the network or broker.
"""

from __future__ import annotations

import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autotrader")
    sub = parser.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="backtest a strategy over historical bars")
    bt.add_argument("symbols", nargs="+", help="tickers, e.g. SPY QQQ")
    bt.add_argument("--start", required=True)
    bt.add_argument("--end", required=True)
    bt.add_argument(
        "--strategy", choices=["momentum", "mean_reversion", "screener"], default="momentum"
    )
    bt.add_argument("--cash", type=float, default=10_000.0)

    run = sub.add_parser("run", help="one trading pass now (or --schedule to loop)")
    run.add_argument("--schedule", action="store_true", help="run the scheduler loop")

    sub.add_parser("flatten", help="close all open positions immediately")

    sc = sub.add_parser("screen", help="rank today's NASDAQ screener candidates")
    sc.add_argument("--top", type=int, default=20, help="how many candidates to show")
    sc.add_argument("--limit", type=int, default=300, help="universe size (most liquid)")
    return parser


def _make_strategy(name: str):
    from autotrader.strategy.mean_reversion import MeanReversionStrategy
    from autotrader.strategy.momentum import MomentumStrategy
    from autotrader.strategy.screener import ScreenerStrategy

    return {
        "mean_reversion": MeanReversionStrategy,
        "screener": ScreenerStrategy,
        "momentum": MomentumStrategy,
    }.get(name, MomentumStrategy)()


def _cmd_backtest(args) -> int:  # pragma: no cover - integration wiring
    from autotrader.backtest.runner import run_backtest
    from autotrader.data.loader import load_bars

    bars = load_bars(args.symbols, args.start, args.end)
    if not bars:
        print("no data loaded for the given symbols/window", file=sys.stderr)
        return 1
    result = run_backtest(bars, _make_strategy(args.strategy), starting_cash=args.cash)
    print(result)
    return 0


def _cmd_run(args) -> int:  # pragma: no cover - integration wiring
    from autotrader.config import Settings
    from autotrader.live.runner import build_engine, main

    if args.schedule:
        main()
        return 0
    engine = build_engine(Settings.from_env())
    print(engine.run_once())
    return 0


def _cmd_flatten(_args) -> int:  # pragma: no cover - integration wiring
    from autotrader.config import Settings
    from autotrader.live.runner import build_engine

    closed = build_engine(Settings.from_env()).flatten_all()
    print(f"flattened {closed} position(s)")
    return 0


def _cmd_screen(args) -> int:  # pragma: no cover - integration wiring
    import datetime as dt

    from autotrader.data.loader import load_bars, make_eod_fetcher, nasdaq_symbols
    from autotrader.strategy.screener import ScreenerStrategy

    universe = nasdaq_symbols(limit=args.limit)
    end = dt.date.today()
    start = end - dt.timedelta(days=400)
    bars = load_bars(universe, start.isoformat(), end.isoformat(), fetcher=make_eod_fetcher())
    signals = ScreenerStrategy().generate(bars)

    # Keep only each symbol's latest-bar signal, then rank by score.
    latest = []
    for sym, sigs in signals.items():
        last_date = bars[sym].index[-1]
        todays = [s for s in sigs if s.timestamp == last_date]
        if todays:
            latest.append(todays[-1])
    latest.sort(key=lambda s: s.score, reverse=True)

    print(f"{'SYMBOL':8s} {'SCORE':>6s}  {'PATTERN':22s} {'STOP':>10s} {'TARGET':>10s}")
    for s in latest[: args.top]:
        print(
            f"{s.symbol:8s} {s.score:6.2f}  {s.pattern or '':22s} "
            f"{s.stop_loss:10.2f} {s.take_profit:10.2f}"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = build_parser().parse_args(argv)
    dispatch = {
        "backtest": _cmd_backtest,
        "run": _cmd_run,
        "flatten": _cmd_flatten,
        "screen": _cmd_screen,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
