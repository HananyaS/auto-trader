"""Autonomous runner loop.

Phase 7 (see ROADMAP.md). On a schedule (near open/close for a daily-bar
strategy, respecting the market calendar) it runs:

    fetch data -> generate signals -> apply risk -> place/close orders

plus structured logging, a trade journal, daily P&L snapshots, alerts on
trades/errors/kill-switch, and restart-safe state (reconcile with broker first).
"""

from __future__ import annotations


def run_once() -> None:
    """One scheduled iteration of the trading loop.

    TODO(Phase 7): reconcile state, load bars, generate signals, apply risk
    guardrails + sizing, and submit/close orders idempotently.
    """
    raise NotImplementedError("Phase 7: implement the runner loop")


def main() -> None:
    """Entry point: wire up the scheduler (APScheduler) + market calendar."""
    raise NotImplementedError("Phase 7: implement scheduler entry point")
