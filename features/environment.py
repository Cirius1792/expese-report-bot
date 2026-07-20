"""Behave environment hooks for Expense Report Bot BDD tests.

Sets up mocks for external system boundaries (dspy/LLM, telegram PTB),
provides in-memory SQLite repository, and real domain objects.

Follows sociable unit test principles:
- System boundaries mocked: dspy (LLM framework), python-telegram-bot, OpenAI client
- Internal collaborators are real: domain entities, repository, correction store
"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import behave

# -- Mock dspy module (before any adapters are imported) --
import sys as _sys
from datetime import date, datetime
from unittest.mock import MagicMock
from unittest.mock import MagicMock as _MagicMock


class _MockChainOfThought:
    """Configurable mock for dspy.ChainOfThought.

    Each test scenario sets instance.return_value to control the LLM prediction.
    """

    def __init__(self, signature_class: type) -> None:
        self._signature_class = signature_class
        self.return_value: _MagicMock = _MagicMock()

    def __call__(self, **kwargs: object) -> _MagicMock:
        return self.return_value


class _MockPredict:
    """Configurable mock for dspy.Predict."""

    def __init__(self, signature_class: type) -> None:
        self._signature_class = signature_class
        self.return_value: _MagicMock = _MagicMock()

    def __call__(self, **kwargs: object) -> _MagicMock:
        return self.return_value


def _mock_lm_constructor(**kwargs: object) -> _MagicMock:
    return _MagicMock()


mock_dspy = _MagicMock()
mock_dspy.Signature = type("Signature", (), {})
mock_dspy.InputField = _MagicMock()
mock_dspy.OutputField = _MagicMock()
mock_dspy.LM = _mock_lm_constructor
mock_dspy.configure = _MagicMock()
mock_dspy.ChainOfThought = _MockChainOfThought
mock_dspy.Predict = _MockPredict
mock_dspy.dspy = _MagicMock()
mock_dspy.dspy.Predicate = type("Predicate", (), {})

_sys.modules["dspy"] = mock_dspy
_sys.modules["dspy.dspy"] = mock_dspy.dspy


# -- Mock telegram module --
mock_telegram = _MagicMock()
mock_telegram.Update = _MagicMock()
mock_telegram.User = _MagicMock()
mock_telegram.Message = _MagicMock()
mock_telegram.Bot = _MagicMock()
mock_telegram.File = _MagicMock()
mock_telegram.PhotoSize = _MagicMock()
mock_telegram.helpers = _MagicMock()


# InlineKeyboardButton — simple dataclass for test assertions
class _BDDFakeInlineKeyboardButton:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


# InlineKeyboardMarkup — stores the keyboard for test inspection
class _BDDFakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard: list):
        self.inline_keyboard = inline_keyboard


mock_telegram.InlineKeyboardButton = _BDDFakeInlineKeyboardButton
mock_telegram.InlineKeyboardMarkup = _BDDFakeInlineKeyboardMarkup

mock_ext = _MagicMock()
mock_telegram.ext = mock_ext
mock_ext.Application = _MagicMock()
mock_ext.CommandHandler = _MagicMock()
mock_ext.MessageHandler = _MagicMock()
mock_ext.TypeHandler = _MagicMock()


class _MockApplicationHandlerStopError(Exception):
    """Mock PTB ApplicationHandlerStop exception for Behave tests."""

    pass


mock_ext.ApplicationHandlerStop = _MockApplicationHandlerStopError
mock_filters = _MagicMock()
mock_filters.PHOTO = _MagicMock()
mock_filters.TEXT = _MagicMock()
mock_filters.COMMAND = _MagicMock()
mock_ext.filters = mock_filters
mock_context_types = _MagicMock()
mock_context_types.DEFAULT_TYPE = _MagicMock()
mock_ext.ContextTypes = mock_context_types

_sys.modules["telegram"] = mock_telegram
_sys.modules["telegram.ext"] = mock_ext

# -- Now safe to import project modules --  # noqa: E402
from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository  # noqa: E402
from expense_report.domain.correction_state import CorrectionStore  # noqa: E402


def before_all(context: "behave.runner.Context") -> None:
    """Set up environment variables for the entire test run."""
    context.config.setup_logging()
    os.environ.setdefault("LLM_BASE_URL", "http://mock-llm:8080")
    os.environ.setdefault("LLM_API_KEY", "mock-api-key")
    os.environ.setdefault("LLM_MODEL", "mock-model")


def before_scenario(context: "behave.runner.Context", scenario: "behave.model.Scenario") -> None:
    """Set up fresh test fixtures before each scenario."""
    # In-memory SQLite repository (fresh per scenario)
    context.repository = SqliteExpenseRepository(":memory:")

    # Real correction store (domain object, not mocked)
    context.correction_store = CorrectionStore()

    # Test data defaults
    context.user_id = 123456789
    context.current_date = date(2026, 7, 15)
    context.current_datetime = datetime(2026, 7, 15, 12, 0, 0)

    # Temporary directory for authorization audit log
    context.authorization_tempdir = TemporaryDirectory()
    context.unauthorized_log_path = Path(context.authorization_tempdir.name) / "unauthorized.log"

    # Telegram mock helpers (used by telegram step definitions)
    context.telegram_updates: list[MagicMock] = []
    context.telegram_replies: list[str] = []
    context.telegram_documents: list[tuple[str, bytes]] = []

    # Reset CSV content and extraction adapter state
    context._csv_content = None
    context.extraction_result = None
    context.last_prediction = None


def after_scenario(context: "behave.runner.Context", scenario: "behave.model.Scenario") -> None:
    """Clean up after each scenario."""
    # Close SQLite connection
    if hasattr(context, "repository"):
        context.repository._conn.close()

    # Clean up authorization temp directory
    if hasattr(context, "authorization_tempdir"):
        context.authorization_tempdir.cleanup()
