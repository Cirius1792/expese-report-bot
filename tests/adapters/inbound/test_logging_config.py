"""Tests for logging configuration in the main entry point.

Verifies LOG_LEVEL env var handling, defaults, and fallback behavior.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock, patch


class TestConfigureLogging:
    """Tests for _configure_logging in main.py."""

    @patch.dict(os.environ, {}, clear=True)
    def test_default_log_level_is_info(self) -> None:
        """When LOG_LEVEL is not set, logging level defaults to INFO."""
        # Reload module to pick up fresh env
        import importlib

        from expense_report.adapters.inbound import main as main_module

        importlib.reload(main_module)

        effective_level = main_module._configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert effective_level == "INFO"

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True)
    def test_valid_log_level_accepted(self) -> None:
        """When LOG_LEVEL is set to a valid value, it's used."""
        import importlib

        from expense_report.adapters.inbound import main as main_module

        importlib.reload(main_module)

        effective_level = main_module._configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
        assert effective_level == "DEBUG"

    @patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True)
    def test_invalid_log_level_falls_back_to_info(self) -> None:
        """When LOG_LEVEL is invalid, falls back to INFO and logs a warning."""
        import importlib

        from expense_report.adapters.inbound import main as main_module

        importlib.reload(main_module)

        effective_level = main_module._configure_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        assert effective_level == "INFO"

    @patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True)
    @patch("logging.warning")
    @patch("logging.basicConfig")
    def test_invalid_log_level_emits_warning(
        self,
        mock_basic_config: object,
        mock_warning: MagicMock,
    ) -> None:
        """Invalid LOG_LEVEL emits a warning with the invalid value."""
        import importlib

        from expense_report.adapters.inbound import main as main_module

        importlib.reload(main_module)

        main_module._configure_logging()

        mock_warning.assert_called_once()
        args, _ = mock_warning.call_args
        # Format string contains INVALID in a positional arg
        all_args = " ".join(str(a) for a in args)
        assert "INVALID" in all_args


class TestMainStartsLogging:
    """Tests that main() configures logging before adapters."""

    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "fake:token",
            "EXPENSE_DB_PATH": "/tmp/expenses.db",
            "UNAUTHORIZED_LOG_PATH": "/tmp/unauthorized.log",
        },
        clear=True,
    )
    def test_logging_configured_before_adapters(self) -> None:
        """main() configures logging before creating adapters.

        We verify by checking that a logger exists at the expected level
        after main() is called. We patch Application to prevent actual
        Telegram connection.
        """
        from unittest.mock import MagicMock, patch

        import expense_report.adapters.inbound.main as main_module

        call_order: list[str] = []

        def configure_logging() -> str:
            call_order.append("configure_logging")
            return "INFO"

        def load_authorized_users() -> frozenset[int]:
            call_order.append("load_authorized_users")
            return frozenset({123456789})

        def build_audit(*args: object, **kwargs: object) -> MagicMock:
            call_order.append("audit")
            audit = MagicMock()
            audit.verify_writable.side_effect = lambda: call_order.append("audit_verify")
            return audit

        def register_authorization_guard(*args: object, **kwargs: object) -> None:
            call_order.append("register_authorization_guard")

        def build_extraction() -> MagicMock:
            call_order.append("extraction_adapter")
            return MagicMock()

        def build_repository(*args: object, **kwargs: object) -> MagicMock:
            call_order.append("repository")
            return MagicMock()

        def build_expense_recording_use_case(*args: object, **kwargs: object) -> MagicMock:
            call_order.append("expense_recording_use_case")
            return MagicMock()

        def build_application() -> MagicMock:
            call_order.append("application_builder")
            mock_builder_instance = MagicMock()
            mock_app = MagicMock()
            mock_app.run_polling.side_effect = lambda: call_order.append("run_polling")
            mock_builder_instance.token.return_value.build.return_value = mock_app
            return mock_builder_instance

        def register_handlers(*args: object, **kwargs: object) -> None:
            call_order.append("register_handlers")

        with (
            patch.object(main_module, "_configure_logging", side_effect=configure_logging),
            patch.object(
                main_module,
                "load_authorized_user_ids_from_env",
                side_effect=load_authorized_users,
            ),
            patch.object(main_module, "UnauthorizedAttemptAudit", side_effect=build_audit),
            patch.object(
                main_module,
                "register_authorization_guard",
                side_effect=register_authorization_guard,
            ),
            patch(
                "expense_report.adapters.inbound.main.DspyExtractionAdapter",
                side_effect=build_extraction,
            ),
            patch(
                "expense_report.adapters.inbound.main.SqliteExpenseRepository",
                side_effect=build_repository,
            ),
            patch(
                "expense_report.adapters.inbound.main.ExpenseRecordingUseCase",
                side_effect=build_expense_recording_use_case,
            ),
            patch(
                "expense_report.adapters.inbound.main.Application.builder",
                side_effect=build_application,
            ),
            patch.object(main_module, "register_handlers", side_effect=register_handlers),
        ):
            main_module.main()

        assert call_order == [
            "configure_logging",
            "load_authorized_users",
            "audit",
            "audit_verify",
            "extraction_adapter",
            "repository",
            "expense_recording_use_case",
            "application_builder",
            "register_authorization_guard",
            "register_handlers",
            "run_polling",
        ]
