"""CLI commands for expense extraction (stories 1-2).

Provides three subcommands:
- extract-from-image IMAGE_PATH
- extract-from-pdf PDF_PATH
- extract-from-text TEXT

Accepts --user-id and --db options. All subcommands route through the
ExpenseRecordingUseCase driving port in ONE_SHOT mode.
"""

from __future__ import annotations

import argparse

from expense_report.domain.models import ExtractionResult
from expense_report.domain.source_types import SourceType

# CLI entry point — lazy imports for adapters to avoid circular deps
# at module level and keep import errors contained


def _print_extraction_result(source_label: str, result: ExtractionResult) -> None:
    """Print a formatted extraction result to stdout.

    This helper is intentionally narrow — it takes only a string label and an
    ExtractionResult from the domain model. It must NOT import any application
    or expense-recording symbols.
    """
    print(f"Extraction result from '{source_label}':")
    print(f"  Amount:   {result.amount}")
    print(f"  Currency: {result.currency}")
    print(f"  Merchant: {result.merchant}")
    print(f"  Date:     {result.date}")
    print(f"  Category: {result.category}")
    print(f"  Complete: {result.is_complete}")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Extract structured expense data from receipts and text."
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=999999999,
        help="Telegram user ID (default: 999999999 for CLI testing)",
    )
    parser.add_argument(
        "--db",
        default="expenses.db",
        help="SQLite database path (default: expenses.db)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    img_parser = subparsers.add_parser(
        "extract-from-image", help="Extract expense from a receipt image"
    )
    img_parser.add_argument("image_path", type=str, help="Path to the image file")

    txt_parser = subparsers.add_parser("extract-from-text", help="Extract expense from free text")
    txt_parser.add_argument("text", type=str, help="Free-text expense description")

    pdf_parser = subparsers.add_parser(
        "extract-from-pdf", help="Extract expense from a PDF receipt"
    )
    pdf_parser.add_argument("pdf_path", type=str, help="Path to the PDF file")

    return parser


def main() -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    from expense_report.adapters.out.dspy_extraction import DspyExtractionAdapter
    from expense_report.adapters.out.source_preparation import SourcePreparationAdapter
    from expense_report.adapters.out.sqlite_repository import (
        SqliteExpenseRepository,
    )
    from expense_report.application.correction_state import CorrectionStore
    from expense_report.application.expense_recording import (
        ExpenseRecordingUseCase,
    )
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
        SourceRejected,
    )

    extractor = DspyExtractionAdapter()
    repo = SqliteExpenseRepository(args.db)
    preparation = SourcePreparationAdapter()
    expense_recording = ExpenseRecordingUseCase(preparation, extractor, repo, CorrectionStore())

    source: str | bytes
    source_type: SourceType
    if args.command == "extract-from-image":
        with open(args.image_path, "rb") as f:
            source = f.read()
        source_type = SourceType.IMAGE
        source_label = args.image_path
    elif args.command == "extract-from-pdf":
        with open(args.pdf_path, "rb") as f:
            source = f.read()
        source_type = SourceType.PDF
        source_label = args.pdf_path
    else:
        source = args.text
        source_type = SourceType.TEXT
        source_label = args.text

    outcome = expense_recording.record(
        RecordExpense(
            user_id=args.user_id,
            source=source,
            source_type=source_type,
            mode=RecordingMode.ONE_SHOT,
            receipt_photo_id=None,
        )
    )
    if isinstance(outcome, SourceRejected):
        print(outcome.reason)
        raise SystemExit(1)
    if isinstance(outcome, ExpenseRecorded):
        result = outcome.extraction
    elif isinstance(outcome, ExtractionIncomplete):
        result = outcome.extraction
    else:
        raise AssertionError(f"Unexpected ONE_SHOT outcome: {type(outcome).__name__}")

    _print_extraction_result(source_label, result)

    if isinstance(outcome, ExpenseRecorded):
        print(f"\nSaved expense: {outcome.expense}")
    else:
        print("\nExtraction incomplete — not saved.")
