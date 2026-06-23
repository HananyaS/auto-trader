"""Alerting (Phase 7/8 ops). A ``Notifier`` is called on trades, errors, and the
kill-switch so an autonomous system is never unsupervised.

``TelegramNotifier`` posts to the Telegram Bot API. The HTTP send is injectable so
the message-building logic is testable without network; at runtime it uses stdlib
``urllib`` (no extra dependency). Alerting must never crash trading, so the engine
calls notifiers defensively.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol


class Notifier(Protocol):
    def notify(self, message: str) -> None: ...


class TelegramNotifier:
    """Send alerts to a Telegram chat via a bot token + chat id."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        *,
        sender: Callable[[str, dict], None] | None = None,
    ) -> None:
        if not bot_token or not chat_id:
            raise ValueError("TelegramNotifier requires both bot_token and chat_id")
        self._token = bot_token
        self._chat_id = chat_id
        self._sender = sender or self._http_send

    @property
    def url(self) -> str:
        return f"https://api.telegram.org/bot{self._token}/sendMessage"

    def notify(self, message: str) -> None:
        self._sender(self.url, {"chat_id": self._chat_id, "text": message})

    @staticmethod
    def _http_send(url: str, payload: dict) -> None:  # pragma: no cover - network
        import urllib.request

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)  # noqa: S310 - fixed Telegram API host
