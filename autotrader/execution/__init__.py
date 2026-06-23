"""Execution: broker-agnostic order interface + Alpaca adapter (paper first).

``SimBroker`` is an in-memory implementation for tests/dry-runs; ``AlpacaBroker``
is the real paper/live adapter. Both satisfy the ``Broker`` protocol.
"""

from autotrader.execution.broker import Broker, Order, Position
from autotrader.execution.sim import SimBroker

__all__ = ["Broker", "Order", "Position", "SimBroker"]
