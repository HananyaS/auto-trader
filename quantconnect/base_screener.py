# region imports
from AlgorithmImports import *  # noqa: F403  (provided by the LEAN/QC runtime)
# endregion


class SymbolData:
    """Per-symbol state: ATR, strategy indicators, and a rolling window of bars.

    Indicators returned by ``make_indicators`` are QC auto-registered indicators
    (e.g. ``self.RSI(...)``) — LEAN updates them every bar, and we warm them from
    history so a newly-added universe member is usable quickly (no look-ahead).
    The rolling window serves patterns that need raw bars (volume highs, gaps).
    """

    def __init__(self, algorithm, symbol, window_size=30):
        self.algorithm = algorithm
        self.symbol = symbol
        self.window = RollingWindow[TradeBar](window_size)  # noqa: F405
        self.atr = algorithm.ATR(symbol, 14, MovingAverageType.Wilders, Resolution.Daily)  # noqa: F405
        self.indicators = algorithm.make_indicators(symbol)  # {name: indicator}

        for ind in [self.atr, *self.indicators.values()]:
            algorithm.WarmUpIndicator(symbol, ind, Resolution.Daily)
        history = list(algorithm.History[TradeBar](symbol, window_size, Resolution.Daily))  # noqa: F405
        for bar in history:  # oldest -> newest; RollingWindow[0] ends up newest
            self.window.Add(bar)

    def on_bar(self, bar):
        self.window.Add(bar)

    @property
    def ready(self):
        return (
            self.window.IsReady
            and self.atr.IsReady
            and all(i.IsReady for i in self.indicators.values())
        )


class ScreenerAlgorithm(QCAlgorithm):  # noqa: F405
    """Reusable spine for a daily-bar, 1-2 day-hold, multi-symbol screener.

    Subclasses implement just two hooks: ``make_indicators(symbol) -> dict`` and
    ``signal(symbol, sd) -> (score, stop, target) | None``. Universe selection,
    scheduling, ranked entries, sizing, and stop/target/time exits are shared so
    each strategy file stays tiny and directly comparable.
    """

    # --- tunables (override per strategy or via self.GetParameter) ---
    # Broad coarse/fine universe over the WHOLE US market (survivorship-bias-free,
    # point-in-time) — kept liquid enough to actually trade, incl. mid/small caps.
    universe_size = 500          # most-liquid names kept after the liquidity floor
    min_price = 5.0              # avoid sub-$5 / penny stocks
    min_dollar_volume = 5e6      # liquidity floor (lower -> reaches more mid/small caps)
    max_positions = 10           # concurrent positions
    risk_per_trade = 0.01        # equity risked per trade (entry-stop distance)
    max_position_pct = 0.10      # notional cap per position
    max_hold_days = 2            # time-based exit horizon
    window_size = 30             # rolling-bar window per symbol

    def Initialize(self):
        self.SetStartDate(2010, 1, 1)
        self.SetEndDate(2022, 1, 1)        # reserve 2022+ as an UNTOUCHED hold-out
        self.SetCash(100_000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)  # noqa: F405
        self.UniverseSettings.Resolution = Resolution.Daily  # noqa: F405
        self.SetWarmUp(timedelta(days=300))  # noqa: F405

        self.AddEquity("SPY", Resolution.Daily)  # schedule anchor + benchmark  # noqa: F405
        self.SetBenchmark("SPY")
        self.AddUniverse(self._coarse, self._fine)

        self._data = {}        # symbol -> SymbolData
        self._entry_date = {}  # symbol -> entry time (for the time-exit)

        self.configure()       # subclass hook for param overrides

        self.Schedule.On(
            self.DateRules.EveryDay("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", 15),
            self._rebalance,
        )

    # --- universe -----------------------------------------------------------

    def _coarse(self, coarse):
        liquid = [
            c for c in coarse
            if c.HasFundamentalData and c.Price > self.min_price
            and c.DollarVolume > self.min_dollar_volume
        ]
        liquid.sort(key=lambda c: c.DollarVolume, reverse=True)
        return [c.Symbol for c in liquid[: self.universe_size]]

    def _fine(self, fine):
        return [f.Symbol for f in fine]  # override for sector/market-cap screens

    def OnSecuritiesChanged(self, changes):
        for security in changes.AddedSecurities:
            symbol = security.Symbol
            if symbol.Value == "SPY" or symbol in self._data:
                continue
            self._data[symbol] = SymbolData(self, symbol, self.window_size)
        for security in changes.RemovedSecurities:
            self._data.pop(security.Symbol, None)

    def OnData(self, data):
        for symbol, sd in self._data.items():
            bar = data.Bars.get(symbol)
            if bar is not None:
                sd.on_bar(bar)

    # --- the daily screen ---------------------------------------------------

    def _rebalance(self):
        if self.IsWarmingUp:
            return

        # 1) Time-based exits first (frees slots/capital). Stops/targets fire on their own.
        for symbol, entered in list(self._entry_date.items()):
            if not self.Portfolio[symbol].Invested:
                self._entry_date.pop(symbol, None)
            elif (self.Time - entered).days >= self.max_hold_days:
                self.Liquidate(symbol, tag="max_hold")
                self._entry_date.pop(symbol, None)

        open_slots = self.max_positions - len(self._entry_date)
        if open_slots <= 0:
            return

        # 2) Rank fresh candidates by score; enter the best until slots/limits bind.
        candidates = []
        for symbol, sd in self._data.items():
            if self.Portfolio[symbol].Invested or not sd.ready:
                continue
            sig = self.signal(symbol, sd)
            if sig and sig[0] > 0 and sig[1] < self.Securities[symbol].Price < sig[2]:
                candidates.append((symbol, sig))
        candidates.sort(key=lambda c: c[1][0], reverse=True)

        for symbol, (score, stop, target) in candidates[:open_slots]:
            price = self.Securities[symbol].Price
            qty = self._position_size(price, stop, score)
            if qty < 1:
                continue
            self.MarketOrder(symbol, qty)
            self.StopMarketOrder(symbol, -qty, stop, tag="stop")
            self.LimitOrder(symbol, -qty, target, tag="target")
            self._entry_date[symbol] = self.Time

    def _position_size(self, price, stop, score):
        """Fixed-fractional sizing, capped by notional, scaled by conviction."""
        equity = self.Portfolio.TotalPortfolioValue
        per_share_risk = max(price - stop, 1e-6)
        qty = min((equity * self.risk_per_trade) / per_share_risk,
                  (equity * self.max_position_pct) / price)
        return int(qty * (0.5 + 0.5 * min(max(score, 0.0), 1.0)))  # score-scaled

    # --- hooks the subclasses implement ------------------------------------

    def configure(self):
        """Optional: override tunables (e.g. from self.GetParameter)."""

    def make_indicators(self, symbol):
        """Return {name: auto-registered indicator} for this symbol."""
        return {}

    def signal(self, symbol, sd):
        """Return (score in (0,1], stop_price, target_price) to enter, else None."""
        raise NotImplementedError
