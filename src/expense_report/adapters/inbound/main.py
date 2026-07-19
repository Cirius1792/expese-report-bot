"""Main entry point for the Telegram expense report bot.

Reads TELEGRAM_BOT_TOKEN and optional EXPENSE_DB_PATH from environment.
Initializes adapters, registers handlers, and starts polling.
"""

from __future__ import annotations

import os

from telegram.ext import Application

from expense_report.adapters.inbound.telegram_bot import register_handlers
from expense_report.adapters.out.dspy_extraction import DspyExtractionAdapter
from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository
from expense_report.domain.correction_state import CorrectionStore


def main() -> None:
    """Start the Telegram bot."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    db_path = os.environ.get("EXPENSE_DB_PATH", "expenses.db")

    extraction = DspyExtractionAdapter()
    repository = SqliteExpenseRepository(db_path=db_path)
    correction_store = CorrectionStore()

    app = Application.builder().token(token).build()
    register_handlers(app, extraction, repository, correction_store)
    app.run_polling()
