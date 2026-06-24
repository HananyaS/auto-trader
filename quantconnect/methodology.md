# Searching many strategies without fooling yourself

You want to "test many strategies until one performs great." That process **manufactures fake
winners** unless you control for it: try 20 random strategies and the best will look great by luck
alone. This is the single most important page in this folder.

## The five rules

1. **Reserve a hold-out and never peek.** Each algorithm sets `SetEndDate(2022,1,1)`, leaving
   2022→present untouched. Do **all** searching/tuning on pre-2022. Run the hold-out **once**, at
   the very end, on your 1–2 finalists. If a finalist falls apart on the hold-out, it was overfit —
   believe the hold-out, not the search.

2. **Walk-forward, not one split.** Use QC **Optimization** to tune parameters on a rolling train
   window and score on the *next* (unseen) window; step forward; repeat. A real edge is a broad
   plateau across windows, not a single lucky parameter spike.

3. **Correct for multiple testing.** Track **N** = how many strategy×parameter combinations you
   tried. A Sharpe that's impressive for one try is noise after 200 tries. Apply a **Deflated
   Sharpe Ratio** (or, crudely, Bonferroni: require p < 0.05/N). Rule of thumb: the more you search,
   the higher the bar the survivor must clear.

4. **Beat two benchmarks, not zero.**
   - **SPY buy & hold** over the same window — "is it worth the capital?" (compare *exposure-adjusted*;
     these strategies sit mostly in cash, so also look at return-per-unit-exposure and Sharpe, not
     just raw return).
   - **A random-entry null** of the same trade count + holding — "is the *selection* skillful, or
     just market drift?" Only entries that beat random have an edge.

5. **Demand a sane sample.** 20 trades prove nothing. Want ≥ ~100 trades and a per-trade return
   whose confidence interval excludes zero before taking a result seriously.

## Reusing this repo's tooling on QC output
Export a strategy's QC trade list (CSV) and post-process with the harness already in this repo
(`autotrader/backtest/metrics.py`, `autotrader/backtest/evaluate.py`):
- `expectancy`, `profit_factor`, `t_stat`, `bootstrap_ci` → per-trade significance.
- `percentile_rank(strategy_return, null_returns)` → edge vs the random null.
- `random_entry_benchmark` → build the null distribution on the same universe/window.

## A disciplined search loop
1. Pick a strategy; sweep its params with QC Optimization on **pre-2022 walk-forward** only.
2. Keep it only if it beats **both** benchmarks with a significant per-trade CI and enough trades.
3. Penalize by how many configs you tried (deflated Sharpe).
4. Survivors (ideally 1–2) → run **once** on the 2022+ hold-out. Ship only if it holds up.
5. Then **paper-trade** before risking real money — backtests are necessary, never sufficient.
