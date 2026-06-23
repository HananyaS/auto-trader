# auto-trader

An autonomous short-term (≈1–2 day holding period) trading system for US stocks/ETFs,
built in Python and validated through a **backtest → paper → live** pipeline.

This repo is at the planning stage. The build is laid out as a step-by-step to-do list in
**[ROADMAP.md](./ROADMAP.md)** — start there.

## Quick orientation
- **Market:** US stocks/ETFs
- **Horizon:** ~1–2 day swing holds
- **Strategy:** rule-based baseline first (momentum / mean-reversion); ML deferred until proven
- **Broker:** Alpaca (same API for paper and live)
- **Principle:** prove the edge on history and on paper before risking real capital

See [ROADMAP.md](./ROADMAP.md) for the full phased plan and checklists.
