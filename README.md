# auto-trader

An autonomous short-term (≈1–2 day holding period) trading system for **US stocks/ETFs**,
built in Python and validated through a **backtest → paper → live** pipeline.

The full build is laid out as a step-by-step to-do list in **[ROADMAP.md](./ROADMAP.md)**.

## Quick orientation
- **Market:** S&P 500 stocks
- **Horizon:** ~1–2 day swing holds
- **Strategy:** two rule-based baselines (momentum + mean-reversion); keep whichever backtests
  better. ML deferred until a baseline is proven.
- **Backtester:** backtrader
- **Broker:** Alpaca (same API for paper and live), PDT-aware for accounts under $25k
- **Principle:** prove the edge on history and on paper before risking real capital

## Project structure
```
autotrader/
  __main__.py      # CLI: python -m autotrader run|flatten|backtest
  config.py        # settings + secrets loading (env / .env), risk limits
  data/            # market data fetch + caching            (Phase 2)
  strategy/        # pure signal functions: momentum, mean_reversion (Phase 3)
  backtest/        # backtrader runner + metrics             (Phase 4)
  risk/            # position sizing + guardrails (PDT-aware)(Phase 5)
  execution/       # broker-agnostic interface + Alpaca + SimBroker (Phase 6)
  live/            # autonomous engine, scheduler, Telegram alerts  (Phase 7)
tests/             # pytest suite (60 tests, no network needed)
```
Phases 0–7 are implemented and tested; Phases 8–9 are operational (paper → live) and need your
keys, network, and time — see the runbook below.

## Getting started (development)
```bash
# 1. (recommended) create a virtualenv
python3 -m venv .venv && source .venv/bin/activate

# 2. install with dev tooling
pip install -e ".[dev]"

# 3. configure secrets
cp .env.example .env       # then fill in your Alpaca PAPER keys

# 4. run the tests + linter
pytest
ruff check .
```

Keep `ALPACA_ENV=paper` until the strategy is validated. The real `.env` is gitignored —
never commit credentials.

> Note: live data/trading needs outbound network access (Yahoo Finance for yfinance,
> `*.alpaca.markets` for the broker). In a locked-down/sandboxed environment these hosts must be
> allowlisted; the full test suite runs offline regardless.

## CLI

```bash
# 1) Validate the edge offline (run for BOTH strategies, compare to buy & hold)
python -m autotrader backtest SPY QQQ AAPL --start 2022-01-01 --end 2024-01-01 --strategy momentum
python -m autotrader backtest SPY QQQ AAPL --start 2022-01-01 --end 2024-01-01 --strategy mean_reversion

# 2) Paper trading: one pass now, or run the scheduler loop (weekdays after the close)
python -m autotrader run
python -m autotrader run --schedule

# 3) Safety override: close every open position immediately
python -m autotrader flatten
```

## Runbook: backtest → paper → live

1. **Backtest (Phase 4).** Run both strategies over a multi-year window, judge **out-of-sample**
   vs buy-and-hold SPY *after costs*. Keep the better baseline. Only proceed if it clears your
   success criteria.
2. **Paper (Phase 8).** Set Alpaca **paper** keys in `.env` (`ALPACA_ENV=paper`), optionally add
   `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` for alerts, then `python -m autotrader run --schedule`.
   Let it trade for several weeks. Review the JSONL journal (`journal/trades.jsonl`) and compare
   fills to backtest expectations.
3. **Live (Phase 9).** Once paper meets your criteria, switch `.env` to **live** keys
   (`ALPACA_ENV=live`) and start with **small capital** — same code path. Keep the kill-switch and
   risk limits on, watch the alerts, and remember `python -m autotrader flatten` for a fast exit.
   Scale up only as live tracks expectations.

Safety built in: fixed-fractional sizing capped per position, max concurrent positions, max
exposure, a daily-loss **kill-switch**, **PDT-awareness** (<$25k), idempotent orders
(restart-safe), and reconcile-with-broker each pass.

See [ROADMAP.md](./ROADMAP.md) for the full phased plan and current progress.
