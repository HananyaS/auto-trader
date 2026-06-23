"""Signal generation as pure functions (bars -> signals).

Kept pure so the *same* logic runs identically in backtest and live. Two
baselines are implemented and compared in backtest; we keep whichever performs
better on the 1-2 day horizon (see ROADMAP.md, Phase 3).
"""

from autotrader.strategy.base import Signal, SignalSet, Strategy

__all__ = ["Signal", "SignalSet", "Strategy"]
