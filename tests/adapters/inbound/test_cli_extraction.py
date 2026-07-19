"""Tests for CLI extraction commands.

Uses sociable unit tests: real SqliteExpenseRepository and DspyExtractionAdapter
(no mocking of internal collaborators). Only system boundaries are mocked:
dspy.ChainOfThought (LLM framework), openai.OpenAI (vision API), PIL.Image (image lib).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


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


class TestMainSociable:
    """End-to-end CLI tests with real adapters, mocked only at system boundaries.

    Uses SqliteExpenseRepository on a temp file (not mocked) and
    DspyExtractionAdapter (real class) with dspy.ChainOfThought/OpenAI patched.
    """

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.ChainOfThought")
    @patch("expense_report.adapters.inbound.cli_extraction.datetime")
    def test_text_flow_prints_result_and_saves(
        self,
        mock_dt: MagicMock,
        mock_chain: MagicMock,
        capsys: Any,
        tmp_path: Any,
    ) -> None:
        """extract-from-text prints extraction result and saves to the database."""
        # Arrange: configure chain of thought to return a complete prediction
        mock_prediction = MagicMock()
        mock_prediction.amount = "15.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Restaurant"
        mock_prediction.date = "2026-07-15"
        mock_prediction.category = "food"
        mock_chain.return_value = MagicMock(return_value=mock_prediction)

        db_path = str(tmp_path / "test.db")

        from expense_report.adapters.inbound.cli_extraction import main

        # Act
        with patch(
            "sys.argv",
            ["expense-extract", "--db", db_path, "extract-from-text", "15 eur restaurant"],
        ):
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            main()

        # Assert: output was printed
        captured = capsys.readouterr()
        assert "Extraction result from '15 eur restaurant'" in captured.out
        assert "Complete: True" in captured.out

        # Assert: expense was actually saved to the database
        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(db_path)
        results = repo.get_by_user_and_month(user_id=999999999, year=2026, month=7)
        assert len(results) == 1
        saved = results[0]
        assert saved.amount == Decimal("15.00")
        assert saved.currency == "EUR"
        assert saved.merchant == "Restaurant"
        assert saved.date == date(2026, 7, 15)
        assert saved.category == "food"
        assert saved.user_id == 999999999

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("expense_report.adapters.out.dspy_extraction.OpenAI")
    @patch("PIL.Image.open")
    @patch("expense_report.adapters.inbound.cli_extraction.datetime")
    def test_image_flow_saves_to_database(
        self,
        mock_dt: MagicMock,
        mock_image_open: MagicMock,
        mock_openai_cls: MagicMock,
        capsys: Any,
        tmp_path: Any,
    ) -> None:
        """extract-from-image loads image bytes, extracts, and saves to database."""
        # Arrange: mock PIL image processing
        mock_img = MagicMock()

        def fake_save(buf: Any, format: str, quality: int) -> str:
            return buf.write(b"fake-jpeg-data")  # type: ignore[func-returns-value]

        mock_img.save.side_effect = fake_save
        mock_image_open.return_value = mock_img

        # Arrange: mock OpenAI vision API response
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"amount":"29.99","currency":"USD","merchant":"Store","date":"2026-07-10","category":""}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Create a fake image file
        image_path = tmp_path / "receipt.jpg"
        image_path.write_bytes(b"fake-image-content")
        db_path = str(tmp_path / "test.db")

        from expense_report.adapters.inbound.cli_extraction import main

        # Act
        with patch(
            "sys.argv",
            [
                "expense-extract",
                "--db",
                db_path,
                "extract-from-image",
                str(image_path),
            ],
        ):
            mock_dt.now.return_value = datetime(2026, 7, 10, 14, 0, 0)
            main()

        # Assert: output was printed
        captured = capsys.readouterr()
        assert "Extraction result from" in captured.out
        assert "29.99" in captured.out

        # Assert: expense was actually saved to the database
        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(db_path)
        results = repo.get_by_user_and_month(user_id=999999999, year=2026, month=7)
        assert len(results) == 1
        saved = results[0]
        assert saved.amount == Decimal("29.99")
        assert saved.currency == "USD"
        assert saved.merchant == "Store"
        assert saved.date == date(2026, 7, 10)
        assert saved.category is None
