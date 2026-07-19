"""Global test configuration — provides a mock dspy module for all tests.

dspy-ai is not installed in this environment (no network access). This conftest
creates a minimal mock dspy module so that adapter modules can be imported
without the real dspy package. Individual tests patch dspy.LM, dspy.configure,
and dspy.ChainOfThought for their specific scenarios.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

# Create a mock dspy module that satisfies import dspy
mock_dspy = MagicMock()

# Ensure dspy.Signature, dspy.InputField, dspy.OutputField are mockable
mock_dspy.Signature = type("Signature", (), {})
mock_dspy.InputField = MagicMock()
mock_dspy.OutputField = MagicMock()
mock_dspy.LM = MagicMock()
mock_dspy.configure = MagicMock()
mock_dspy.ChainOfThought = MagicMock()

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
