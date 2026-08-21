"""Application orchestration for Expense Recording — including the Correction lifecycle."""

from __future__ import annotations

import logging
from datetime import datetime

from expense_report.application.correction_state import CorrectionStore
from expense_report.domain.correction_state import PendingCorrection
from expense_report.domain.models import Expense, ExtractionResult
from expense_report.domain.source_types import SourceType
from expense_report.ports.expense_recording import (
    CorrectionLimitReached,
    CorrectionOpened,
    CorrectionResolved,
    CorrectionStillIncomplete,
    ExpenseRecorded,
    ExtractionIncomplete,
    RecordExpense,
    RecordingMode,
    RecordingOutcome,
    SourceRejected,
)
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort
from expense_report.ports.source_preparation import (
    SourcePreparationError,
    SourcePreparationPort,
)

logger = logging.getLogger(__name__)


def _build_expense(
    result: ExtractionResult,
    user_id: int,
    receipt_photo_id: str | None,
) -> Expense:
    """Construct an Expense domain object from a complete ExtractionResult.

    Extracted to avoid duplicating the construction in the fresh-recording
    and Correction-resolve paths.
    """
    assert result.amount is not None and result.currency is not None
    assert result.merchant is not None and result.date is not None
    return Expense(
        id=None,
        amount=result.amount,
        currency=result.currency,
        merchant=result.merchant,
        date=result.date,
        category=result.category,
        user_id=user_id,
        receipt_photo_id=receipt_photo_id,
        created_at=datetime.now(),
    )


class ExpenseRecordingUseCase:
    """Extract, validate completeness, construct, and persist an Expense.

    Owns the Correction lifecycle: pending-state routing, refine/extract
    dispatch, attempt counting, max-out, and state cleanup.
    """

    def __init__(
        self,
        preparation: SourcePreparationPort,
        extraction: ExtractionPort,
        repository: ExpenseRepositoryPort,
        correction_store: CorrectionStore,
    ) -> None:
        self._preparation = preparation
        self._extraction = extraction
        self._repository = repository
        self._store = correction_store

    def record(self, command: RecordExpense) -> RecordingOutcome:
        # ── Correction routing: only for CONVERSATIONAL text ──
        if command.mode == RecordingMode.CONVERSATIONAL and command.source_type == SourceType.TEXT:
            pending = self._store.get(command.user_id)
            if pending is not None:
                if pending.maxed_out:
                    logger.info(
                        "Correction maxed out for user %s (attempt %s/3), clearing",
                        command.user_id,
                        pending.attempt_count,
                    )
                    self._store.remove(command.user_id)
                    return CorrectionLimitReached()

                logger.info(
                    "Correction received from user %s (attempt %s/3)",
                    command.user_id,
                    pending.attempt_count,
                )
                assert isinstance(command.source, str)
                refined = self._extraction.refine(pending.original_result, command.source)

                if refined.is_complete:
                    # Correction resolved: save (receipt_photo_id always None), clear
                    expense = _build_expense(refined, command.user_id, None)
                    saved_expense = self._repository.save(expense)
                    self._store.remove(command.user_id)
                    logger.info(
                        "Correction resolved for user %s: saved updated expense",
                        command.user_id,
                    )
                    return CorrectionResolved(expense=saved_expense, extraction=refined)

                # Still incomplete: increment attempt, keep original result
                updated = PendingCorrection(
                    user_id=command.user_id,
                    original_result=pending.original_result,
                    attempt_count=pending.attempt_count + 1,
                )
                self._store.set(command.user_id, updated)
                logger.info(
                    "Correction still incomplete for user %s (attempt %s)",
                    command.user_id,
                    updated.attempt_count,
                )
                return CorrectionStillIncomplete(
                    extraction=refined,
                    attempt_count=updated.attempt_count,
                )

        # ── Fresh recording (ONE_SHOT, CONVERSATIONAL without pending, any source) ──
        try:
            view = self._preparation.prepare(command.source, command.source_type)
        except SourcePreparationError as exc:
            logger.info(
                "Source rejected for user %s: %s",
                command.user_id,
                exc.message,
            )
            return SourceRejected(reason=str(exc.message))

        result = self._extraction.extract(view)

        if result.is_complete:
            expense = _build_expense(result, command.user_id, command.receipt_photo_id)
            saved_expense = self._repository.save(expense)
            return ExpenseRecorded(expense=saved_expense, extraction=result)

        # Incomplete fresh extraction
        if command.mode == RecordingMode.CONVERSATIONAL:
            self._store.set(
                command.user_id,
                PendingCorrection(
                    user_id=command.user_id,
                    original_result=result,
                ),
            )
            return CorrectionOpened(extraction=result)

        return ExtractionIncomplete(extraction=result)
