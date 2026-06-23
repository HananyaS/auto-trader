"""Signal generation as pure functions (bars -> signals).

Kept pure so the *same* logic runs identically in backtest and live. Two
baselines are implemented and compared in backtest; we keep whichever performs
better on the 1-2 day horizon (see ROADMAP.md, Phase 3).
"""

from autotrader.strategy.base import Side, Signal, SignalSet, Strategy
from autotrader.strategy.mean_reversion import MeanReversionStrategy
from autotrader.strategy.momentum import MomentumStrategy

__all__ = [
    "Side",
    "Signal",
    "SignalSet",
    "Strategy",
    "MomentumStrategy",
    "MeanReversionStrategy",
]
