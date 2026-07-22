"""Tests for CLI extraction commands.

Uses sociable unit tests: real SqliteExpenseRepository and DspyExtractionAdapter
(no mocking of internal collaborators). Only system boundaries are mocked:
dspy.ChainOfThought (LLM framework), openai.OpenAI (vision API), PIL.Image (image lib).
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import date, datetime
from decimal import Decimal
from types import ModuleType
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
    @patch("expense_report.application.expense_recording.datetime")
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

        # Assert: output was printed with exact full string
        captured = capsys.readouterr()
        assert captured.out == (
            "Extraction result from '15 eur restaurant':\n"
            "  Amount:   15.00\n"
            "  Currency: EUR\n"
            "  Merchant: Restaurant\n"
            "  Date:     2026-07-15\n"
            "  Category: food\n"
            "  Complete: True\n"
            "\n"
            "Saved expense: Expense(id=1, amount=Decimal('15.00'), currency='EUR',"
            " merchant='Restaurant', date=datetime.date(2026, 7, 15),"
            " category='food', user_id=999999999, receipt_photo_id=None,"
            " created_at=datetime.datetime(2026, 7, 15, 12, 0))\n"
        )

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

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    def test_text_flow_translates_arguments_to_record_command(self) -> None:
        """extract-from-text constructs correct RecordExpense command via use case."""
        from expense_report.domain.models import Expense, ExtractionResult
        from expense_report.ports.expense_recording import (
            ExpenseRecorded,
            RecordExpense,
            RecordingMode,
        )

        result = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
        )
        saved = Expense(
            id=9,
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
            user_id=42,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )

        with (
            patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
            patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository"),
            patch(
                "expense_report.application.expense_recording.ExpenseRecordingUseCase"
            ) as use_case_class,
            patch(
                "sys.argv",
                [
                    "expense-extract",
                    "--user-id",
                    "42",
                    "extract-from-text",
                    "15 eur restaurant",
                ],
            ),
        ):
            use_case_class.return_value.record.return_value = ExpenseRecorded(saved, result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        use_case_class.return_value.record.assert_called_once_with(
            RecordExpense(
                user_id=42,
                source="15 eur restaurant",
                source_type="text",
                mode=RecordingMode.ONE_SHOT,
                receipt_photo_id=None,
            )
        )

    def test_text_flow_renders_incomplete_without_saving(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """extract-from-text with incomplete extraction prints message and does not save."""
        from expense_report.domain.models import ExtractionResult
        from expense_report.ports.expense_recording import ExtractionIncomplete

        result = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant=None,
            date=date(2026, 7, 15),
            category=None,
        )

        with (
            patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
            patch(
                "expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository"
            ) as repo_class,
            patch(
                "expense_report.application.expense_recording.ExpenseRecordingUseCase"
            ) as use_case_class,
            patch(
                "sys.argv",
                ["expense-extract", "extract-from-text", "15 eur"],
            ),
        ):
            use_case_class.return_value.record.return_value = ExtractionIncomplete(result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        captured = capsys.readouterr()
        assert captured.out == (
            "Extraction result from '15 eur':\n"
            "  Amount:   15.00\n"
            "  Currency: EUR\n"
            "  Merchant: None\n"
            "  Date:     2026-07-15\n"
            "  Category: None\n"
            "  Complete: False\n"
            "\n"
            "Extraction incomplete — not saved.\n"
        )
        repo_class.return_value.save.assert_not_called()

    def test_image_flow_does_not_use_expense_recording(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """extract-from-image does not import expense_recording port or application modules."""
        image_path = tmp_path / "receipt.jpg"
        image_path.write_bytes(b"fake-image-content")
        db_path = str(tmp_path / "test.db")

        from expense_report.domain.models import ExtractionResult

        # Eject pre-loaded copies so we can detect new imports during main()
        saved_modules: dict[str, ModuleType] = {}
        for mod_name in (
            "expense_report.application.expense_recording",
            "expense_report.ports.expense_recording",
        ):
            if mod_name in sys.modules:
                saved_modules[mod_name] = sys.modules.pop(mod_name)

        try:
            with (
                patch(
                    "expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"
                ) as mock_extractor_cls,
                patch(
                    "expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository"
                ) as mock_repo_cls,
                patch("expense_report.adapters.inbound.cli_extraction.datetime") as mock_dt,
                patch(
                    "sys.argv",
                    [
                        "expense-extract",
                        "--db",
                        db_path,
                        "extract-from-image",
                        str(image_path),
                    ],
                ),
            ):
                mock_extractor = mock_extractor_cls.return_value
                mock_extractor.extract.return_value = ExtractionResult(
                    amount=Decimal("29.99"),
                    currency="USD",
                    merchant="Store",
                    date=date(2026, 7, 10),
                    category=None,
                )
                mock_dt.now.return_value = datetime(2026, 7, 10, 14, 0, 0)

                from expense_report.adapters.inbound.cli_extraction import main

                main()

            # Prove neither expense_recording module was imported during image flow
            assert "expense_report.application.expense_recording" not in sys.modules, (
                "Image path must not import expense_report.application.expense_recording"
            )
            assert "expense_report.ports.expense_recording" not in sys.modules, (
                "Image path must not import expense_report.ports.expense_recording"
            )

            # Prove the legacy image path still works and persists
            mock_repo_cls.return_value.save.assert_called_once()
            captured = capsys.readouterr()
            assert "Extraction result from" in captured.out
            assert "29.99" in captured.out
        finally:
            for mod_name, mod in saved_modules.items():
                sys.modules[mod_name] = mod
