"""Tests for CLI extraction commands.

Uses sociable unit tests: real SqliteExpenseRepository and DspyExtractionAdapter
(no mocking of internal collaborators). Only system boundaries are mocked:
dspy.ChainOfThought (LLM framework), openai.OpenAI (vision API), PIL.Image (image lib).
"""

from __future__ import annotations

import os
import pathlib
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _make_pdf(num_pages: int) -> bytes:
    """Generate an in-memory multi-page PDF with Pillow (no binary fixtures)."""
    buf = BytesIO()
    pages = [
        Image.new("RGB", (60, 80), color=((page_index * 60) % 256, 30, 30))
        for page_index in range(num_pages)
    ]
    pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


class TestArgparseSetup:
    """Verify argparse creates correct subparsers."""

    def test_parse_extract_from_pdf(self) -> None:
        """extract-from-pdf subparser accepts PDF_PATH argument."""
        from expense_report.adapters.inbound.cli_extraction import build_parser

        parser = build_parser()
        args = parser.parse_args(["extract-from-pdf", "/path/to/receipt.pdf"])

        assert args.command == "extract-from-pdf"
        assert args.pdf_path == "/path/to/receipt.pdf"
        assert args.user_id == 999999999  # default
        assert args.db == "expenses.db"  # default

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
    @patch("expense_report.application.expense_recording.datetime")
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
        from expense_report.domain.source_types import SourceType
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
                source_type=SourceType.TEXT,
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

    def test_image_flow_translates_arguments_to_record_command(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """extract-from-image constructs correct RecordExpense command via use case."""
        from expense_report.domain.models import Expense, ExtractionResult
        from expense_report.domain.source_types import SourceType
        from expense_report.ports.expense_recording import (
            ExpenseRecorded,
            RecordExpense,
            RecordingMode,
        )

        image_path = tmp_path / "receipt.jpg"
        image_path.write_bytes(b"fake-image-content")

        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 10),
            category=None,
        )
        saved = Expense(
            id=9,
            amount=Decimal("29.99"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 10),
            category=None,
            user_id=42,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 10, 14, 0, 0),
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
                    "extract-from-image",
                    str(image_path),
                ],
            ),
        ):
            use_case_class.return_value.record.return_value = ExpenseRecorded(saved, result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        use_case_class.return_value.record.assert_called_once_with(
            RecordExpense(
                user_id=42,
                source=b"fake-image-content",
                source_type=SourceType.IMAGE,
                mode=RecordingMode.ONE_SHOT,
                receipt_photo_id=None,
            )
        )

    def test_image_flow_renders_incomplete_without_saving(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """extract-from-image with incomplete extraction prints message and does not save."""
        from expense_report.domain.models import ExtractionResult
        from expense_report.ports.expense_recording import ExtractionIncomplete

        image_path = tmp_path / "receipt.jpg"
        image_path.write_bytes(b"fake-image-content")

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
                ["expense-extract", "extract-from-image", str(image_path)],
            ),
        ):
            use_case_class.return_value.record.return_value = ExtractionIncomplete(result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        captured = capsys.readouterr()
        assert captured.out == (
            f"Extraction result from '{image_path}':\n"
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
    @patch("expense_report.application.expense_recording.datetime")
    def test_pdf_flow_prints_result_and_saves(
        self,
        mock_dt: MagicMock,
        mock_image_open: MagicMock,
        mock_openai_cls: MagicMock,
        capsys: Any,
        tmp_path: Any,
    ) -> None:
        """extract-from-pdf renders the PDF, extracts, and saves to the database.

        Sociable test: real SourcePreparationAdapter (real pypdfium2 against a
        Pillow-generated PDF) and real SqliteExpenseRepository; only the vision
        API and image library are mocked at the system boundary.
        """
        mock_img = MagicMock()

        def fake_save(buf: Any, format: str, quality: int) -> str:
            return buf.write(b"fake-jpeg-data")  # type: ignore[func-returns-value]

        mock_img.save.side_effect = fake_save
        mock_image_open.return_value = mock_img

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=(
                        '{"amount":"42.50","currency":"EUR","merchant":"PDF Shop",'
                        '"date":"2026-07-11","category":""}'
                    )
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Two-page PDF written to disk; renderable by real pypdfium2
        pdf_path = tmp_path / "receipt.pdf"
        pdf_path.write_bytes(_make_pdf(2))
        db_path = str(tmp_path / "test.db")

        from expense_report.adapters.inbound.cli_extraction import main

        with patch(
            "sys.argv",
            [
                "expense-extract",
                "--db",
                db_path,
                "--user-id",
                "42",
                "extract-from-pdf",
                str(pdf_path),
            ],
        ):
            mock_dt.now.return_value = datetime(2026, 7, 11, 14, 0, 0)
            main()

        # Exactly one vision request carrying 2 image parts (one per page)
        create_call = mock_client.chat.completions.create
        assert create_call.call_count == 1
        messages = create_call.call_args[1]["messages"]
        image_parts = [part for part in messages[0]["content"] if part["type"] == "image_url"]
        assert len(image_parts) == 2

        captured = capsys.readouterr()
        assert "Extraction result from" in captured.out
        assert "42.50" in captured.out
        assert "Saved expense:" in captured.out

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(db_path)
        results = repo.get_by_user_and_month(user_id=42, year=2026, month=7)
        assert len(results) == 1
        saved = results[0]
        assert saved.amount == Decimal("42.50")
        assert saved.merchant == "PDF Shop"
        assert saved.receipt_photo_id is None

    def test_pdf_flow_translates_arguments_to_record_command(
        self,
        tmp_path: pathlib.Path,
    ) -> None:
        """extract-from-pdf constructs correct RecordExpense command via use case."""
        from expense_report.domain.models import Expense, ExtractionResult
        from expense_report.domain.source_types import SourceType
        from expense_report.ports.expense_recording import (
            ExpenseRecorded,
            RecordExpense,
            RecordingMode,
        )

        pdf_path = tmp_path / "receipt.pdf"
        pdf_path.write_bytes(b"fake-pdf-content")

        result = ExtractionResult(
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="PDF Shop",
            date=date(2026, 7, 11),
            category=None,
        )
        saved = Expense(
            id=9,
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="PDF Shop",
            date=date(2026, 7, 11),
            category=None,
            user_id=42,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 11, 14, 0, 0),
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
                    "extract-from-pdf",
                    str(pdf_path),
                ],
            ),
        ):
            use_case_class.return_value.record.return_value = ExpenseRecorded(saved, result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        use_case_class.return_value.record.assert_called_once_with(
            RecordExpense(
                user_id=42,
                source=b"fake-pdf-content",
                source_type=SourceType.PDF,
                mode=RecordingMode.ONE_SHOT,
                receipt_photo_id=None,
            )
        )

    def test_pdf_rejection_prints_reason_and_exits_one(
        self,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """SourceRejected from a PDF prints the reason and exits with code 1."""
        from expense_report.ports.expense_recording import SourceRejected

        pdf_path = tmp_path / "too-big.pdf"
        pdf_path.write_bytes(b"fake-pdf-content")

        with (
            patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
            patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository"),
            patch(
                "expense_report.application.expense_recording.ExpenseRecordingUseCase"
            ) as use_case_class,
            patch(
                "sys.argv",
                ["expense-extract", "extract-from-pdf", str(pdf_path)],
            ),
        ):
            use_case_class.return_value.record.return_value = SourceRejected(
                reason=(
                    "Your PDF has 8 pages. Only PDFs with up to 5 pages are accepted,"
                    " so your request will not be satisfied."
                )
            )
            from expense_report.adapters.inbound.cli_extraction import main

            with pytest.raises(SystemExit) as excinfo:
                main()

        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "8 pages" in captured.out
        assert "5 pages" in captured.out
        assert "not be satisfied" in captured.out
