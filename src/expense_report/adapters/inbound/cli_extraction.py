"""CLI commands for expense extraction (stories 1-2).

Provides two subcommands:
- extract-from-image IMAGE_PATH
- extract-from-text TEXT

Accepts --user-id and --db options. Uses DspyExtractionAdapter for extraction
and SqliteExpenseRepository for persistence.
"""

from __future__ import annotations

import argparse
from datetime import datetime

from expense_report.domain.models import Expense, ExtractionResult

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

    return parser


def main() -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    from expense_report.adapters.out.dspy_extraction import DspyExtractionAdapter
    from expense_report.adapters.out.sqlite_repository import (
        SqliteExpenseRepository,
    )

    # ── Image path: legacy extraction + direct persist (no expense_recording imports) ──
    if args.command == "extract-from-image":
        extractor = DspyExtractionAdapter()
        repo = SqliteExpenseRepository(args.db)

        with open(args.image_path, "rb") as f:
            source = f.read()

        result = extractor.extract(source, "image")

        _print_extraction_result(args.image_path, result)

        if result.is_complete:
            assert result.amount is not None and result.currency is not None
            assert result.merchant is not None and result.date is not None

            expense = Expense(
                id=None,
                amount=result.amount,
                currency=result.currency,
                merchant=result.merchant,
                date=result.date,
                category=result.category,
                user_id=args.user_id,
                receipt_photo_id=None,
                created_at=datetime.now(),
            )

            saved = repo.save(expense)
            print(f"\nSaved expense: {saved}")
        else:
            print("\nExtraction incomplete — not saved.")
        return

    # ── Text path: expense recording use case (all expense_recording imports here) ──
    from expense_report.application.expense_recording import (
        ExpenseRecordingUseCase,
    )
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
    )

    extractor = DspyExtractionAdapter()
    repo = SqliteExpenseRepository(args.db)
    expense_recording = ExpenseRecordingUseCase(extractor, repo)

    outcome = expense_recording.record(
        RecordExpense(
            user_id=args.user_id,
            source=args.text,
            source_type="text",
            mode=RecordingMode.ONE_SHOT,
            receipt_photo_id=None,
        )
    )
    result = outcome.extraction

    _print_extraction_result(args.text, result)

    if isinstance(outcome, ExpenseRecorded):
        print(f"\nSaved expense: {outcome.expense}")
    else:
        print("\nExtraction incomplete — not saved.")
