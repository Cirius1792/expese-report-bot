"""Telegram user authorization helpers for the inbound adapter.

This module owns Telegram-specific authorization, whitelist configuration,
and the dedicated unauthorized-attempt audit file.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Coroutine
from datetime import UTC, datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

logger = logging.getLogger(__name__)


class UnauthorizedAttemptAudit:
    """Append unauthorized Telegram user attempts to a plain-text audit file."""

    def __init__(
        self,
        log_path: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_path = Path(log_path)
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        """Return the audit file path."""
        return self._log_path

    def record(self, user_id: int) -> None:
        """Append one unauthorized-attempt line with the Telegram user ID."""
        with self._log_path.open("a", encoding="utf-8") as file:
            file.write(f"{self._timestamp()} user_id={user_id}\n")

    def _timestamp(self) -> str:
        current = self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_authorization_guard(
    authorized_user_ids: Collection[int],
    audit: UnauthorizedAttemptAudit,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[object, object, None]]:
    """Create a PTB callback that stops unauthorized Telegram updates.

    Returns an async function suitable for use with TypeHandler or
    as a middleware-style filter. Authorized updates pass through
    unchanged; unauthorized updates are audited and stopped.
    """
    authorized = frozenset(authorized_user_ids)

    async def authorization_guard(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if update.effective_user is None:
            logger.debug("Stopping Telegram update with no effective user")
            raise ApplicationHandlerStop

        user_id = int(update.effective_user.id)
        if user_id in authorized:
            return

        audit.record(user_id)
        raise ApplicationHandlerStop

    return authorization_guard
