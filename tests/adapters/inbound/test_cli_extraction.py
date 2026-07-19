"""Tests for CLI extraction commands."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from expense_report.domain.models import Expense, ExtractionResult


class TestArgparseSetup:
    """Verify argparse creates correct subparsers."""

    def test_parse_extract_from_image(self) -> None:
        """extract-from-image subparser accepts IMAGE_PATH argument."""
        from expense_report.adapters.inbound.cli_extraction import build_parser

        parser = build_parser()
        args = parser.parse_args(["extract-from-image", "/path/to/receipt.jpg"])

        assert args.command == "extract-from-image"
        assert args.image_path == "/path/to/receipt.jpg"
        assert args.user_id == 999999999  # default
        assert args.db == "expenses.db"  # default

    def test_parse_extract_from_text(self) -> None:
        """extract-from-text subparser accepts TEXT argument."""
        from expense_report.adapters.inbound.cli_extraction import build_parser

        parser = build_parser()
        args = parser.parse_args(["extract-from-text", "lunch 15 eur"])

        assert args.command == "extract-from-text"
        assert args.text == "lunch 15 eur"
        assert args.user_id == 999999999  # default

    def test_allows_custom_user_id_and_db(self) -> None:
        """--user-id and --db options are accepted by both subcommands."""
        from expense_report.adapters.inbound.cli_extraction import build_parser

        parser = build_parser()
        args = parser.parse_args(
            [
                "--user-id",
                "42",
                "--db",
                "/tmp/test.db",
                "extract-from-text",
                "test expense",
            ]
        )

        assert args.user_id == 42
        assert args.db == "/tmp/test.db"
        assert args.command == "extract-from-text"

    def test_requires_subcommand(self) -> None:
        """Running without a subcommand exits with error."""
        from expense_report.adapters.inbound.cli_extraction import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestMainWithMocks:
    """End-to-end flow with mocked adapters."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter")
    @patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository")
    @patch("expense_report.adapters.inbound.cli_extraction.datetime")
    def test_text_flow_prints_result_and_saves(
        self,
        mock_dt: MagicMock,
        mock_repo_cls: MagicMock,
        mock_adapter_cls: MagicMock,
        capsys: Any,
    ) -> None:
        """extract-from-text prints extraction result and saves expense."""
        # Arrange
        mock_adapter = MagicMock()
        mock_adapter.extract.return_value = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
        )
        mock_adapter_cls.return_value = mock_adapter

        mock_repo = MagicMock()
        mock_repo.save.return_value = Expense(
            id="saved-id-001",
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
            user_id=999999999,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )
        mock_repo_cls.return_value = mock_repo

        from expense_report.adapters.inbound.cli_extraction import main

        # Act
        with patch(
            "sys.argv", ["expense-extract", "extract-from-text", "15 eur restaurant"]
        ):
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            main()

        # Assert
        mock_adapter.extract.assert_called_once_with(
            "15 eur restaurant", "text"
        )
        mock_repo.save.assert_called_once()
        saved_arg = mock_repo.save.call_args[0][0]
        assert isinstance(saved_arg, Expense)
        assert saved_arg.amount == Decimal("15.00")
        assert saved_arg.merchant == "Restaurant"

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter")
    @patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository")
    @patch("expense_report.adapters.inbound.cli_extraction.datetime")
    def test_image_flow_loads_file_and_extracts(
        self,
        mock_dt: MagicMock,
        mock_repo_cls: MagicMock,
        mock_adapter_cls: MagicMock,
        capsys: Any,
        tmp_path: Any,
    ) -> None:
        """extract-from-image loads image bytes and calls adapters."""
        # Create a temp image file
        image_path = tmp_path / "receipt.jpg"
        image_path.write_bytes(b"fake-image-content")

        mock_adapter = MagicMock()
        mock_adapter.extract.return_value = ExtractionResult(
            amount=Decimal("29.99"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 10),
            category=None,
        )
        mock_adapter_cls.return_value = mock_adapter

        mock_repo = MagicMock()
        mock_repo.save.return_value = Expense(
            id="img-exp-001",
            amount=Decimal("29.99"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 10),
            category=None,
            user_id=999999999,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 10, 14, 0, 0),
        )
        mock_repo_cls.return_value = mock_repo

        from expense_report.adapters.inbound.cli_extraction import main

        # Act
        with patch(
            "sys.argv",
            ["expense-extract", "extract-from-image", str(image_path)],
        ):
            mock_dt.now.return_value = datetime(2026, 7, 10, 14, 0, 0)
            main()

        # Assert
        mock_adapter.extract.assert_called_once_with(
            b"fake-image-content", "image"
        )
        mock_repo.save.assert_called_once()
