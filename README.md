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
  config.py        # settings + secrets loading (env / .env), risk limits
  data/            # market data fetch + caching            (Phase 2)
  strategy/        # pure signal functions: momentum, mean_reversion (Phase 3)
  backtest/        # backtrader runner + metrics             (Phase 4)
  risk/            # position sizing + guardrails (PDT-aware)(Phase 5)
  execution/       # broker-agnostic interface + Alpaca      (Phase 6)
  live/            # autonomous scheduler/runner loop        (Phase 7)
tests/             # pytest suite
```
Modules beyond `config.py` are interface scaffolds with `NotImplementedError` stubs; each is
filled in at the phase noted above.

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

See [ROADMAP.md](./ROADMAP.md) for the full phased plan and current progress.
