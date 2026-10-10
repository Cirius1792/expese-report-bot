"""main() must migrate the database before constructing the repository (ADR 0013)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from expense_report.adapters.inbound.cli_extraction import main
from expense_report.ports.expense_recording import SourceRejected


def test_main_migrates_before_opening_the_database() -> None:
    """The repository is only constructed after `liquibase update` has run."""
    order: list[str] = []

    with (
        patch(
            "expense_report.adapters.inbound.cli_extraction.ensure_database_migrated",
            side_effect=lambda db_path: order.append("migrate"),
        ),
        patch(
            "expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository",
            side_effect=lambda db_path: order.append("open") or MagicMock(),
        ),
        patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
        patch("expense_report.application.expense_recording.ExpenseRecordingUseCase") as use_case,
        patch("sys.argv", ["expense-extract", "extract-from-text", "coffee 3.50 eur"]),
    ):
        use_case.return_value.record.return_value = SourceRejected(reason="stub")

        with pytest.raises(SystemExit):
            main()

    assert order == ["migrate", "open"]
