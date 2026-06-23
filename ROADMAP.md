# Roadmap: Autonomous Short-Term (1–2 Day) Stock/ETF Trading System

A step-by-step to-do list for building an **autonomous** swing-trading system that holds
US stocks/ETFs for roughly **1–2 days**, written in **Python**, validated through a
**backtest → paper → live** pipeline.

**Guiding principle: prove the edge on history and on paper before risking a dollar.**
Most retail auto-trading projects fail not on engineering but on (a) overfit backtests and
(b) ignored transaction costs / risk controls. The sequencing below is deliberately defensive
about both.

## Key decisions (locked)
- **Strategy:** build **both** a momentum and a mean-reversion baseline as pure signal
  functions, compare them in backtest, and keep whichever performs better on the 1–2 day
  horizon. **Defer ML** until a rule-based baseline is profitable in paper trading.
- **Universe:** **S&P 500 stocks** (mind survivorship bias when backtesting).
- **Backtester:** **backtrader** (event-driven, realistic fills).
- **Broker/data:** **Alpaca** — free paper-trading account with the *same* API as live,
  commission-free, fractional shares, Python SDK (`alpaca-py`). One code path for paper and live.
  (Interactive Brokers via `ib_insync` is the heavier-duty alternative.)
- **Capital / regulatory:** account **under $25k** → **PDT-aware** (max 3 day-trades / 5
  sessions). A 1–2 day *hold* usually avoids same-day round-trips, but position tracking is
  PDT-aware so the bot never gets locked. Paper-first.

---

## Phase 0 — Define the edge & guardrails (before any code)
- [ ] Write a one-paragraph **strategy hypothesis** for each baseline (momentum, mean-reversion).
      A bot needs an explicit edge, not just automation. *(Finalize alongside Phase 3.)*
- [x] Pick a **universe**: **S&P 500 stocks**.
- [ ] Define **entry rules, exit rules, holding period, and position sizing** in plain English.
      *(Holding period = 1–2 days; rules finalized in Phase 3.)*
- [x] Define **risk limits**: encoded as defaults in `config.py` / `.env.example`
      (risk-per-trade, max position %, max concurrent positions, max exposure, daily-loss
      kill-switch, PDT cap).
- [ ] Write **success criteria** to advance between phases (e.g. backtest Sharpe > 1 after costs
      before paper; positive paper P&L over N weeks before live). *(Finalize in Phase 4.)*

## Phase 1 — Project scaffolding ✅
- [x] Initialize Python project: `pyproject.toml`, `.gitignore` (ignores `.env`, data caches,
      `__pycache__`).
- [x] Expand README with orientation + run instructions.
- [x] Package layout under `autotrader/`: `data/`, `strategy/`, `backtest/`, `risk/`,
      `execution/`, `live/`, plus `config.py` and `tests/`.
- [x] **Secrets:** `config.py` loads keys from env / `.env` via `python-dotenv`;
      `.env.example` documents them; real `.env` is gitignored.
- [x] Add `pytest` + `ruff`; config layer has passing tests (`tests/test_config.py`).

## Phase 2 — Market data ✅
- [x] Pull **historical daily bars** via `yfinance` (`_fetch_yfinance`), behind an injectable
      `Fetcher` so Alpaca data can be swapped in later without touching callers.
- [x] Build a **data layer** (`autotrader/data/loader.py`): `load_bars()` fetches, **caches to
      parquet**, refetches when the cache doesn't cover the window, and slices to the request.
- [x] **Data hygiene** (`clean_bars`, pure/tested): split/dividend-adjusted prices
      (`auto_adjust=True`), standardized OHLCV schema, sorted + de-duplicated tz-naive index,
      dropped NaN rows. `sp500_symbols()` sources the universe (with a survivorship-bias note).
- Tests: `tests/test_data_loader.py` (hygiene + cache logic, no network needed).
- ⚠️ Live fetch needs network egress to `query1.finance.yahoo.com` (blocked in this hosted
  env by policy; works locally or once allowlisted).

## Phase 3 — Strategy & signals ✅
- [x] Signals as **pure functions** (`Strategy.generate(bars) -> SignalSet`), side-effect free
      (tested: input bars are never mutated) so backtest and live share one implementation.
- [x] **Both baselines** implemented, long-only, emitting `Signal`s with 1–2 day exit logic
      (stop-loss, take-profit, `max_hold_days`):
  - `MomentumStrategy` — breakout above the prior N-day high (`autotrader/strategy/momentum.py`).
  - `MeanReversionStrategy` — oversold short-period RSI entry (`autotrader/strategy/mean_reversion.py`).
- [x] Pure `indicators` module (`rsi`, `prior_rolling_high`); strategy **parameters are
      constructor args** so Phase 4 can sweep and validate them out-of-sample.
- Tests: `tests/test_strategy.py` (indicators + entry/no-entry behavior on synthetic series).
- *Next: decide entry/exit specifics empirically in Phase 4; finalize the Phase-0 hypothesis once
  backtests pick the better baseline.*

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
