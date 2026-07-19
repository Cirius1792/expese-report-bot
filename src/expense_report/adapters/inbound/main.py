"""Main entry point for the Telegram expense report bot.

Reads TELEGRAM_BOT_TOKEN and optional EXPENSE_DB_PATH from environment.
Initializes adapters, registers handlers, and starts polling.
"""

from __future__ import annotations

import logging
import os
import sys

from telegram.ext import Application

from expense_report.adapters.inbound.authorization import (
    UNAUTHORIZED_LOG_ENV,
    UnauthorizedAttemptAudit,
    load_authorized_user_ids_from_env,
    register_authorization_guard,
    resolve_unauthorized_log_path,
)
from expense_report.adapters.inbound.telegram_bot import register_handlers
from expense_report.adapters.out.dspy_extraction import DspyExtractionAdapter
from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository
from expense_report.domain.correction_state import CorrectionStore

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _configure_logging() -> str:
    """Configure Python stdlib logging from environment variables.

    Reads LOG_LEVEL (default: INFO). Invalid values fall back to INFO
    with a warning. All logs go to stdout so Docker can capture them.

    Returns:
        The effective configured logging level name.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        logging.basicConfig(
            level=logging.INFO,
            stream=sys.stdout,
            force=True,
            format=_LOG_FORMAT,
        )
        logging.warning("Invalid LOG_LEVEL '%s', falling back to INFO", level_name)
        return "INFO"

    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        force=True,
        format=_LOG_FORMAT,
    )
    return logging.getLevelName(level)


def main() -> None:
    """Start the Telegram bot."""
    effective_log_level = _configure_logging()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    db_path = os.environ.get("EXPENSE_DB_PATH", "expenses.db")

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting expense report bot (db_path=%s, log_level=%s)",
        db_path,
        effective_log_level,
    )

    authorized_user_ids = load_authorized_user_ids_from_env()
    unauthorized_log_path = resolve_unauthorized_log_path(
        db_path,
        os.environ.get(UNAUTHORIZED_LOG_ENV),
    )
    unauthorized_audit = UnauthorizedAttemptAudit(unauthorized_log_path)
    unauthorized_audit.verify_writable()
    logger.info(
        "Telegram authorization loaded with %s authorized users; unauthorized log=%s",
        len(authorized_user_ids),
        unauthorized_audit.path,
    )

    extraction = DspyExtractionAdapter()
    repository = SqliteExpenseRepository(db_path=db_path)
    correction_store = CorrectionStore()

    app = Application.builder().token(token).build()
    register_authorization_guard(app, authorized_user_ids, unauthorized_audit)
    register_handlers(app, extraction, repository, correction_store)
    logger.info("Bot started, entering polling loop")
    app.run_polling()
