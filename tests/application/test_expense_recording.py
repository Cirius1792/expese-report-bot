"""Tests for the Expense Recording use case (driving interface)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from expense_report.domain.models import Expense, ExtractionResult
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort


def _complete_extraction() -> ExtractionResult:
    return ExtractionResult(
        amount=Decimal("15.00"),
        currency="EUR",
        merchant="Restaurant",
        date=date(2026, 7, 15),
        category="food",
    )


def _incomplete_extraction() -> ExtractionResult:
    return ExtractionResult(
        amount=Decimal("15.00"),
        currency="EUR",
        merchant=None,
        date=date(2026, 7, 15),
        category=None,
    )


@pytest.mark.parametrize("mode_name", ["ONE_SHOT", "CONVERSATIONAL"])
def test_complete_text_records_expense(mode_name: str) -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = lambda expense: replace(expense, id=41)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )
    command = RecordExpense(
        user_id=12345,
        source="lunch 15 eur",
        source_type="text",
        mode=RecordingMode[mode_name],
    )

    with patch("expense_report.application.expense_recording.datetime") as clock:
        clock.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
        outcome = use_case.record(command)

    assert isinstance(outcome, ExpenseRecorded)
    assert outcome.expense.id == 41
    assert outcome.expense.user_id == 12345
    assert outcome.expense.receipt_photo_id is None
    assert outcome.expense.created_at == datetime(2026, 7, 15, 12, 0, 0)
    assert outcome.extraction == _complete_extraction()
    extraction.extract.assert_called_once_with("lunch 15 eur", "text")
    repository.save.assert_called_once()

    # Verify every field of the Expense passed to repository.save
    saved_expense: Expense = repository.save.call_args.args[0]
    assert saved_expense.id is None  # assigned by repository
    assert saved_expense.amount == Decimal("15.00")
    assert saved_expense.currency == "EUR"
    assert saved_expense.merchant == "Restaurant"
    assert saved_expense.date == date(2026, 7, 15)
    assert saved_expense.category == "food"
    assert saved_expense.user_id == 12345
    assert saved_expense.receipt_photo_id is None


@pytest.mark.parametrize("mode_name", ["ONE_SHOT", "CONVERSATIONAL"])
def test_incomplete_text_returns_without_persisting(mode_name: str) -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _incomplete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="lunch 15 eur",
            source_type="text",
            mode=RecordingMode[mode_name],
        )
    )

    assert outcome == ExtractionIncomplete(extraction=_incomplete_extraction())
    repository.save.assert_not_called()


def test_extraction_exception_propagates() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.side_effect = RuntimeError("extract failed")
    repository = MagicMock(spec=ExpenseRepositoryPort)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    with pytest.raises(RuntimeError, match="extract failed"):
        use_case.record(RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT))


def test_repository_exception_propagates() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = RuntimeError("save failed")
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    with pytest.raises(RuntimeError, match="save failed"):
        use_case.record(RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT))


def test_use_case_satisfies_expense_recording_port() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import ExpenseRecordingPort

    extraction = MagicMock(spec=ExtractionPort)
    repository = MagicMock(spec=ExpenseRepositoryPort)

    assert isinstance(
        ExpenseRecordingUseCase(
            cast(ExtractionPort, extraction),
            cast(ExpenseRepositoryPort, repository),
        ),
        ExpenseRecordingPort,
    )
