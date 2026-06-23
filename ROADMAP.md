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

## Phase 4 — Backtesting (make-or-break) ✅
- [x] Adopt **backtrader** (`autotrader/backtest/runner.py`): `run_backtest(bars, strategy)`
      bridges the pure-function strategies into a `Cerebro` via a thin signal-driven
      `bt.Strategy`. Entries are market orders filled at the **next** bar's open (no look-ahead);
      exits honor per-signal stop / target / `max_hold_days`.
- [x] **Model costs realistically:** percentage **slippage** (proxy for bid/ask spread) +
      commission (≈0 on Alpaca), both configurable on `run_backtest`.
- [x] Metrics: total return, **Sharpe/Sortino** (pure helpers in `metrics.py`), **max
      drawdown**, win rate, trade count, final value (`BacktestResult`).
- [x] Anti-overfit tooling: `train_test_split()` and `buy_and_hold_return()` benchmark helper in
      `metrics.py`.
- Tests: `tests/test_backtest.py` (pure metrics + runner executes/skips trades + empty-feed guard).
- [x] **Ran on real S&P 500 data** (2013–2018, `scripts/backtest_sp500.py` + `load_csv_bars`):
      out-of-sample both baselines are positive after costs (momentum Sharpe ~1.8, mean-reversion
      ~1.8). Surfaced & fixed a real bug — an empty data feed silently halted backtrader.
- [ ] **Gate (still yours):** these numbers carry **selection + survivorship bias** (top-liquidity,
      full-coverage universe chosen with hindsight) and aren't dividend-adjusted, so treat them as
      a plumbing check, not a validated edge. Re-run with point-in-time membership before trusting.

## Phase 5 — Risk & portfolio management ✅
- [x] **Position sizer** (`autotrader/risk/sizing.py`): fixed-fractional risk model
      (risk_per_trade of equity over entry-stop distance), clamped by max_position_pct. **Wired
      into the backtest runner**, so backtest and live size positions identically.
- [x] **Risk guardrails as code** (`autotrader/risk/limits.py`): `RiskState` + `can_open_new_position`
      enforcing global halt flag, daily-loss kill-switch, max concurrent positions, max exposure.
- [x] **PDT-aware** tracking: `would_breach_pdt` against the day-trade count (<$25k accounts).
- Tests: `tests/test_risk.py` (sizing math + every guardrail branch).
- *Note: guardrails are enforced live in Phase 7's runner loop.*

## Phase 6 — Execution layer (paper first) ✅
- [x] Broker-agnostic **execution interface** (`Broker` protocol: `submit_order`, `get_positions`,
      `get_account`, `cancel`).
- [x] **`AlpacaBroker`** (`execution/alpaca.py`): alpaca-py adapter (lazy import), paper/live by
      config only; market + limit orders; surfaces `daytrade_count` / `pattern_day_trader`.
- [x] **`SimBroker`** (`execution/sim.py`): in-memory implementation for tests/dry-runs (avg-price
      tracking, equity, fills).
- [x] **Idempotency / no duplicate orders on restart:** both brokers key on `client_order_id`
      (Alpaca rejects duplicates; SimBroker no-ops and returns the original id).
- Tests: `tests/test_execution.py` (SimBroker fills/idempotency + AlpacaBroker creds guard).
- ⚠️ Live Alpaca calls need network egress to `*.alpaca.markets` (blocked here; works locally
  with paper keys). Reconcile-on-startup is exercised in Phase 7 via `get_positions`.

## Phase 7 — The autonomous runner ✅ (core) / ⏳ (ops hardening)
- [x] **Main loop:** `TradingEngine.run_once()` (`autotrader/live/runner.py`) — reconcile →
      load bars → manage exits → signals → risk + sizing → place entries. Dependency-injected so
      it runs against `SimBroker` + synthetic bars in tests.
- [x] **Scheduler:** `main()` wires `AlpacaBroker` + yfinance + an APScheduler cron job
      (weekdays after the close) gated by a `pandas_market_calendars` trading-day check.
- [x] **Restart-safe / idempotent:** positions reconciled from the broker each pass; orders keyed
      on `client_order_id`; positions with no known exit plan are closed defensively.
- [x] **Persistence:** in-memory trade `journal` of every entry/exit with reason.
- Tests: `tests/test_live.py` (entries, no-pyramiding, halt, max-position cap, stop/max-hold/
  unknown-position exits); verified end-to-end with the real `MomentumStrategy`.
- [x] **Ops hardening:** durable **JSONL trade journal** (`journal_path`); **daily-loss
      kill-switch** with start-of-day equity tracking (`reset_day`); **Telegram alerts**
      (`live/notify.py`, pluggable `Notifier`, failures never crash the loop); manual
      **`flatten_all()`** override; **CLI** (`python -m autotrader run|flatten|backtest`).
- [ ] *Optional later:* API-outage retry/backoff around broker calls; daily P&L snapshot file.

## Phase 8 — Paper trading validation  *(tooling ready; you run it)*
The code is complete and tested; these steps require your Alpaca paper keys, network access,
and weeks of real market time, so they're run-and-observe (not executable in the sandbox).
- [ ] Create an Alpaca **paper** account; put the keys in `.env` with `ALPACA_ENV=paper`.
- [ ] (Optional) Set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` for trade/kill-switch alerts.
- [ ] First, **validate the edge offline**: `python -m autotrader backtest <symbols> --start … --end …`
      for both `--strategy momentum` and `--strategy mean_reversion`; compare vs buy-and-hold SPY
      out-of-sample. Keep the better baseline.
- [ ] Run the scheduler: `python -m autotrader run --schedule` (or one pass with `run`). Let it
      trade paper for several weeks across different conditions.
- [ ] **Compare paper fills to backtest expectations** using the JSONL journal; reconcile gaps
      (slippage assumptions, timing) before risking real money.
- [ ] **Gate:** advance only after paper meets your Phase-0 success criteria.

## Phase 9 — Live (small) & iterate  *(tooling ready; you run it)*
- [ ] Flip `.env` to live Alpaca keys + `ALPACA_ENV=live` (same code path) and start with **small
      capital**.
- [ ] Keep the **kill-switch and risk limits** active; watch the alerts; know
      `python -m autotrader flatten` closes everything fast.
- [ ] **Scale gradually** only as live results track expectations.
- [ ] Iterate; consider **ML only after** the rule-based baseline is proven (same validation
      discipline applies).
- See the **Runbook** in `README.md` for exact commands.

---

## Dependencies (in `pyproject.toml`)
`alpaca-py`, `pandas`, `numpy`, `yfinance`, `backtrader`, `pandas_market_calendars`,
`APScheduler`, `python-dotenv`; dev: `pytest`, `ruff`, `black`. Telegram alerts use stdlib only.

## Status
Phases 0–7 implemented and tested (**60 passing**, ruff clean). Phases 8–9 are operational —
all tooling is built; they require your keys, network access, time, and (for 9) real capital.

## Possible extensions later
- Volatility-adjusted sizing; ATR-based stops.
- Point-in-time S&P 500 membership to remove survivorship bias.
- Paid data feed (e.g. Polygon) for intraday precision; Alpaca data feed in place of yfinance.
- ML overlay — only after the rule-based baseline is proven.
