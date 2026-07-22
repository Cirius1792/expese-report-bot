"""Application orchestration for Expense Recording."""

from __future__ import annotations

from datetime import datetime

from expense_report.domain.models import Expense
from expense_report.ports.expense_recording import (
    ExpenseRecorded,
    ExtractionIncomplete,
    RecordExpense,
    RecordingOutcome,
)
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort


class ExpenseRecordingUseCase:
    """Extract, validate completeness, construct, and persist an Expense."""

    def __init__(
        self,
        extraction: ExtractionPort,
        repository: ExpenseRepositoryPort,
    ) -> None:
        self._extraction = extraction
        self._repository = repository

    def record(self, command: RecordExpense) -> RecordingOutcome:
        result = self._extraction.extract(command.source, command.source_type)
        if not result.is_complete:
            return ExtractionIncomplete(extraction=result)

        assert result.amount is not None and result.currency is not None
        assert result.merchant is not None and result.date is not None
        expense = Expense(
            id=None,
            amount=result.amount,
            currency=result.currency,
            merchant=result.merchant,
            date=result.date,
            category=result.category,
            user_id=command.user_id,
            receipt_photo_id=command.receipt_photo_id,
            created_at=datetime.now(),
        )
        saved_expense = self._repository.save(expense)
        return ExpenseRecorded(expense=saved_expense, extraction=result)
