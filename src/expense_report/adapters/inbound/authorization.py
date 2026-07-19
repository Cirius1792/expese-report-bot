"""Telegram user authorization helpers for the inbound adapter.

This module owns Telegram-specific authorization, whitelist configuration,
and the dedicated unauthorized-attempt audit file.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Collection, Coroutine, Mapping
from datetime import UTC, datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, TypeHandler

logger = logging.getLogger(__name__)

AUTHORIZED_USERS_CONFIG_ENV = "AUTHORIZED_USERS_CONFIG_PATH"
UNAUTHORIZED_LOG_ENV = "UNAUTHORIZED_LOG_PATH"


class MalformedAuthorizationConfigError(ValueError):
    """Raised when the authorization config file is not valid JSON."""


def load_authorized_user_ids(config_path: str | None) -> frozenset[int]:
    """Load authorized Telegram user IDs from a JSON whitelist file.

    Missing paths and invalid schemas authorize nobody and log a warning.
    Malformed JSON raises because startup must fail for syntactically broken
    config files.
    """
    if not config_path:
        logger.warning(
            "%s is not set; authorizing no Telegram users",
            AUTHORIZED_USERS_CONFIG_ENV,
        )
        return frozenset()

    path = Path(config_path)
    try:
        raw_content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Could not read authorization config %s (%s); authorizing no Telegram users",
            path,
            exc.__class__.__name__,
        )
        return frozenset()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise MalformedAuthorizationConfigError(
            f"Malformed authorization config JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    if set(data.keys()) != {"authorized_users"}:
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    authorized_users = data.get("authorized_users")
    if not isinstance(authorized_users, list):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    if not all(isinstance(user_id, str) and user_id.isdecimal() for user_id in authorized_users):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    return frozenset(int(user_id) for user_id in authorized_users)


def load_authorized_user_ids_from_env(
    environ: Mapping[str, str] = os.environ,
) -> frozenset[int]:
    """Load authorized Telegram user IDs using AUTHORIZED_USERS_CONFIG_PATH."""
    return load_authorized_user_ids(environ.get(AUTHORIZED_USERS_CONFIG_ENV))


def resolve_unauthorized_log_path(db_path: str, unauthorized_log_path: str | None) -> Path:
    """Resolve the dedicated unauthorized-attempt audit log path."""
    if unauthorized_log_path:
        return Path(unauthorized_log_path)
    return Path(db_path).parent / "unauthorized.log"


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

    def verify_writable(self) -> None:
        """Create the audit file if possible and fail if it is not writable."""
        if not self._log_path.parent.exists():
            raise OSError(
                f"Unauthorized audit log directory does not exist: {self._log_path.parent}"
            )
        with self._log_path.open("a", encoding="utf-8"):
            pass

    def record(self, user_id: int) -> None:
        """Append one unauthorized-attempt line for the given Telegram user ID."""
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
    """Create a PTB callback that stops unauthorized Telegram updates."""
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


def register_authorization_guard(
    app: Application,
    authorized_user_ids: Collection[int],
    audit: UnauthorizedAttemptAudit,
) -> None:
    """Register the global authorization guard before normal Telegram handlers."""
    app.add_handler(
        TypeHandler(Update, make_authorization_guard(authorized_user_ids, audit)),
        group=-1,
    )
