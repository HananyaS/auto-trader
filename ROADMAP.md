# Roadmap: Autonomous Short-Term (1–2 Day) Stock/ETF Trading System

A step-by-step to-do list for building an **autonomous** swing-trading system that holds
US stocks/ETFs for roughly **1–2 days**, written in **Python**, validated through a
**backtest → paper → live** pipeline.

**Guiding principle: prove the edge on history and on paper before risking a dollar.**
Most retail auto-trading projects fail not on engineering but on (a) overfit backtests and
(b) ignored transaction costs / risk controls. The sequencing below is deliberately defensive
about both.

## Key decisions
- **Strategy to start with:** a **rule-based** swing strategy (momentum or short-horizon
  mean-reversion on liquid stocks/ETFs). Transparent and fast to backtest. **Defer ML** until a
  rule-based baseline is profitable in paper trading.
- **Broker/data:** **Alpaca** — free paper-trading account with the *same* API as live,
  commission-free, fractional shares, Python SDK (`alpaca-py`). One code path for paper and live.
  (Interactive Brokers via `ib_insync` is the heavier-duty alternative.)
- **Regulatory:** Under **$25k** in a margin account, the **Pattern Day Trader (PDT)** rule caps
  you at 3 day-trades / 5 days. A 1–2 day *hold* usually avoids same-day round-trips, but make
  position tracking PDT-aware so the bot never gets locked.

---

## Phase 0 — Define the edge & guardrails (before any code)
- [ ] Write a one-paragraph **strategy hypothesis** (e.g. "buy ETFs showing X-day momentum, hold
      1–2 days, exit on target/stop"). A bot needs an explicit edge, not just automation.
- [ ] Pick a **universe**: start small and liquid — large-cap ETFs (SPY, QQQ, sector ETFs) or
      S&P 500 names.
- [ ] Define **entry rules, exit rules, holding period, and position sizing** in plain English.
- [ ] Define **risk limits**: max % per position, max concurrent positions, daily max loss /
      kill-switch, max portfolio exposure. Non-negotiable guardrails.
- [ ] Write **success criteria** to advance between phases (e.g. backtest Sharpe > 1 after costs
      before paper; positive paper P&L over N weeks before live).

## Phase 1 — Project scaffolding
- [ ] Initialize Python project: `pyproject.toml` / `requirements.txt`, virtualenv, `.gitignore`
      (ignore `.env`, data caches, `__pycache__`).
- [ ] Expand this README with strategy hypothesis and run instructions.
- [ ] Package layout: `data/`, `strategy/`, `backtest/`, `risk/`, `execution/`, `live/`,
      `config/`, `tests/`.
- [ ] **Secrets:** API keys in `.env` / env vars via `python-dotenv`. Never commit keys.
- [ ] Add `pytest` + `ruff`/`black`; lightweight CI is a plus.

## Phase 2 — Market data
- [ ] Pull **historical daily (and optional intraday) bars** for your universe (Alpaca data API,
      or `yfinance` for free daily data to prototype).
- [ ] Build a **data layer**: fetch, **cache locally** (parquet/CSV), return clean DataFrames.
- [ ] **Data hygiene:** adjusted prices (splits/dividends), missing bars, timezone alignment to
      US market hours, survivorship-bias awareness.

## Phase 3 — Strategy & signals
- [ ] Implement signals as **pure functions** (`bars -> signals`) so backtest and live are
      identical.
- [ ] Implement the **rule-based baseline** with 1–2 day exit logic (time exit + stop-loss +
      take-profit).
- [ ] Keep **parameters in config**; validate on out-of-sample data to avoid curve-fitting.

## Phase 4 — Backtesting (make-or-break)
- [ ] Adopt a backtester: **`vectorbt`** (fast sweeps) or **`backtrader`** (event-driven). A
      careful custom pandas loop is fine for v1.
- [ ] **Model costs realistically:** slippage + bid/ask spread + partial fills (commissions ≈0 on
      Alpaca). Ignoring these is the #1 cause of backtests that fail in reality.
- [ ] Metrics: return, **Sharpe/Sortino**, **max drawdown**, win rate, avg win/loss, exposure,
      turnover.
- [ ] Anti-overfit: **train/test split or walk-forward**, held-out out-of-sample period, benchmark
      vs buy-and-hold SPY.
- [ ] **Gate:** proceed only if criteria are met *after costs*.

## Phase 5 — Risk & portfolio management
- [ ] **Position sizer** (fixed-fractional or volatility-adjusted) shared by backtest and live.
- [ ] **Risk guardrails as code:** per-trade stop-loss, daily-loss kill-switch, max concurrent
      positions, max exposure, global halt flag.
- [ ] **PDT-aware** position tracking.

## Phase 6 — Execution layer (paper first)
- [ ] Broker-agnostic **execution interface** (`submit_order`, `get_positions`, `get_account`,
      `cancel`); implement with **`alpaca-py` against the paper endpoint**.
- [ ] Order mechanics: order types, **idempotency / no duplicate orders on restart**, state
      reconciliation, retries, partial fills.
- [ ] **Reconcile on startup:** read actual broker positions before acting.

## Phase 7 — The autonomous runner
- [ ] **Main loop / scheduler:** wake on schedule (near open/close for daily bars) → fetch data →
      signals → risk → place/close orders. Use APScheduler/cron; respect the **market calendar**
      (`pandas_market_calendars`).
- [ ] **Logging + persistence:** structured logs, trade journal (DB/CSV), daily P&L snapshots.
- [ ] **Monitoring/alerts:** notify on trades, errors, kill-switch (email/Slack/Telegram).
- [ ] **Resilience:** handle API outages, restart-safe state, manual "flatten all" override.

## Phase 8 — Paper trading validation
- [ ] Run the full system on **Alpaca paper** for several weeks across market conditions.
- [ ] **Compare paper fills to backtest expectations**; reconcile gaps before live.
- [ ] **Gate:** advance only after paper meets Phase-0 criteria.

## Phase 9 — Live (small) & iterate
- [ ] Switch execution to the **live endpoint with small capital** (same code path).
- [ ] Keep kill-switch and daily-loss limits active; monitor closely.
- [ ] **Scale gradually** as live tracks expectations.
- [ ] Iterate; consider **ML only after** the rule-based baseline is proven (same validation
      discipline applies).

---

## Suggested dependencies
`alpaca-py`, `pandas`, `numpy`, `yfinance`, `vectorbt` *or* `backtrader`,
`pandas_market_calendars`, `APScheduler`, `python-dotenv`, `pytest`, `ruff`/`black`.

## Open choices
- Backtesting library: **`vectorbt`** vs **`backtrader`**.
- Baseline strategy: **momentum** vs **mean-reversion** (can prototype both in Phase 3).
- Paid data feed (e.g. Polygon) later for intraday precision.
