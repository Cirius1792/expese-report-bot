"""Global test configuration — provides a mock dspy module for all tests.

dspy-ai is not installed in this environment (no network access). This conftest
creates a functional mock dspy module so that adapter modules can be imported
and DspyExtractionAdapter can be constructed without the real dspy package.

Tests patch dspy.ChainOfThought and/or openai.OpenAI return values for their
specific scenarios. This follows sociable unit test principles: only external
system boundaries (LLM framework, Telegram API) are mocked; internal
collaborators (domain entities, repository, correction store) are real.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock


class _MockChainOfThought:
    """Configurable mock for dspy.ChainOfThought.

    Instances are callable and return a configurable prediction object.
    Tests can set instance.return_value to control what predict() returns.
    """

    def __init__(self, signature_class: type) -> None:
        self._signature_class = signature_class
        self.return_value: MagicMock = MagicMock()

    def __call__(self, **kwargs: object) -> MagicMock:
        return self.return_value


class _MockPredict:
    """Configurable mock for dspy.Predict.

    Instances are callable and return a configurable prediction object.
    """

    def __init__(self, signature_class: type) -> None:
        self._signature_class = signature_class
        self.return_value: MagicMock = MagicMock()

    def __call__(self, **kwargs: object) -> MagicMock:
        return self.return_value


def _mock_lm_constructor(**kwargs: object) -> MagicMock:
    """Mock dspy.LM that accepts any kwargs and returns a MagicMock."""
    return MagicMock()


# Create a mock dspy module that satisfies import dspy
mock_dspy = MagicMock()

# Signature base class for dspy structured extraction
mock_dspy.Signature = type("Signature", (), {})
# InputField/OutputField: called as field defaults in Signature subclasses
mock_dspy.InputField = MagicMock()
mock_dspy.OutputField = MagicMock()
# LM constructor: returns a mock LM instance
mock_dspy.LM = _mock_lm_constructor
# configure: no-op
mock_dspy.configure = MagicMock()
# ChainOfThought: returns a callable that proxies to return_value
mock_dspy.ChainOfThought = _MockChainOfThought
# Predict: returns a callable that proxies to return_value
mock_dspy.Predict = _MockPredict

# Predicate module: needed by some dspy internals
mock_dspy.dspy = MagicMock()
mock_dspy.dspy.Predicate = type("Predicate", (), {})

sys.modules["dspy"] = mock_dspy
sys.modules["dspy.dspy"] = mock_dspy.dspy

# --- Telegram mock ---
# python-telegram-bot is not available without network access.
# Create a minimal mock that allows imports and attribute access.
mock_telegram = MagicMock()

# telegram.Update
mock_update_cls = MagicMock()
mock_telegram.Update = mock_update_cls

# telegram.User
mock_user_cls = MagicMock()
mock_telegram.User = mock_user_cls

# telegram.Message
mock_message_cls = MagicMock()
mock_telegram.Message = mock_message_cls

# telegram.Bot
mock_bot_cls = MagicMock()
mock_telegram.Bot = mock_bot_cls

# telegram.File
mock_file_cls = MagicMock()
mock_telegram.File = mock_file_cls

# telegram.PhotoSize
mock_photo_size_cls = MagicMock()
mock_telegram.PhotoSize = mock_photo_size_cls

# telegram.helpers (if needed)
mock_helpers = MagicMock()
mock_telegram.helpers = mock_helpers

# telegram.ext
mock_ext = MagicMock()
mock_telegram.ext = mock_ext

# telegram.ext.Application
mock_app_cls = MagicMock()
mock_ext.Application = mock_app_cls

# telegram.ext.CommandHandler
mock_command_handler_cls = MagicMock()
mock_ext.CommandHandler = mock_command_handler_cls

# telegram.ext.MessageHandler
mock_message_handler_cls = MagicMock()
mock_ext.MessageHandler = mock_message_handler_cls

# telegram.ext.filters
mock_filters = MagicMock()
mock_filters.PHOTO = MagicMock()
mock_filters.TEXT = MagicMock()
mock_filters.COMMAND = MagicMock()
mock_ext.filters = mock_filters

# telegram.ext.ContextTypes
mock_context_types = MagicMock()
mock_context_types.DEFAULT_TYPE = MagicMock()
mock_ext.ContextTypes = mock_context_types

sys.modules["telegram"] = mock_telegram
sys.modules["telegram.ext"] = mock_ext
