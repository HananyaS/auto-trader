# QuantConnect (LEAN) strategy suite

Upload-ready QC LEAN **Python** algorithms for short-term (1–2 day hold) US-equity screening,
to run/search on QuantConnect's clean, survivorship-bias-free data.

> These files **cannot run in this repo's sandbox** (no LEAN engine / QC data). They're
> syntax-checked here; the real test is a QC backtest. Read **`methodology.md` before searching**
> across strategies — it's what keeps you from "finding" an overfit winner.

## What's here
| File | Strategy | Bucket | Evidence |
|---|---|---|---|
| `base_screener.py` | Shared `ScreenerAlgorithm` spine (universe, schedule, sizing, exits) | — | — |
| `rsi2_mean_reversion.py` | RSI(2) oversold + SMA200 trend filter | mean-reversion | beat our null |
| `bollinger_reversion.py` | Lower-band poke + close back inside, uptrend | mean-reversion | beat our null |
| `volume_spike_breakout.py` | 20-day-high breakout + RVOL≥2 | momentum | best Sharpe / null |
| `gap_reversion.py` | Gap-down that starts to fill | mean-reversion | beat our null |
| `momentum_xsection.py` | Cross-sectional 5-day momentum (top-N) | momentum | QC-enabled |
| `pead.py` | Post-earnings drift (gap+volume **proxy**) | event | QC-enabled |

The four "beat our null" strategies are the patterns that beat a random-entry null out-of-sample in
this repo's local validation harness — evidence-backed starting points, not proven edges.

## How to run on QC
1. New QC Python project → add each file (keep `base_screener.py`; strategies `import` from it).
2. Set the project's **main** to one strategy class at a time (each subclasses `ScreenerAlgorithm`).
3. Backtest. Tunables (`rsi_entry`, `rvol_min`, …) are read via `self.GetParameter(...)`, so you can
   sweep them with QC's **Optimization** without editing code.
4. Each algorithm reserves **2022+ as a hold-out** (`SetEndDate(2022,1,1)`) — keep it untouched
   while you search; only run it once at the very end.

## Confirm against current QC docs before the first run (the API drifts)
- Coarse/fine universe: `CoarseFundamental` (`HasFundamentalData`, `Price`, `DollarVolume`) and
  the `Fundamental`/`FineFundamental` fields (`MarketCap`, sector) — class names have changed
  across LEAN versions.
- `BrokerageName.InteractiveBrokersBrokerage` / `BrokerageName.Alpaca` — set the one you'll deploy to.
- `self.History[TradeBar](...)`, `WarmUpIndicator`, `RollingWindow[TradeBar]`, `self.BB/RSI/SMA/ATR`.

## Notes / gotchas
- **PDT rule**: under $25k a margin account is capped at 3 day-trades / 5 sessions. The 1–2 day
  holds avoid same-day round-trips; backtests use $100k so it's moot — mind it live.
- **Data tier**: strategies 1–4 and momentum run on **free price/volume**. `pead.py` ships as a
  free price/volume *proxy*; the real earnings-data version needs QC fundamental/earnings data
  (possibly a paid tier) — replace the gap/volume trigger with an actual surprise score.
- **Look-ahead**: signals use closed daily bars and the screen runs *before the close*; fills land
  next session. Don't move logic into intraday data without re-checking timing.
- **Fills/fees**: a brokerage model is set so slippage/commissions are modeled; don't trust a
  frictionless backtest.
