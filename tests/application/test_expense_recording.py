"""Tests for the Expense Recording use case (driving interface)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast
from unittest.mock import MagicMock, patch

import pytest

from expense_report.application.correction_state import CorrectionStore
from expense_report.domain.correction_state import PendingCorrection
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
    store = CorrectionStore()
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
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
    assert store.get(12345) is None  # complete fresh recording opens no Correction state

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


def test_incomplete_text_one_shot_returns_without_persisting() -> None:
    """ONE_SHOT incomplete text returns ExtractionIncomplete; no state, no save."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _incomplete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="lunch 15 eur",
            source_type="text",
            mode=RecordingMode.ONE_SHOT,
        )
    )

    assert outcome == ExtractionIncomplete(extraction=_incomplete_extraction())
    repository.save.assert_not_called()
    assert store.get(12345) is None


def test_one_shot_incomplete_never_touches_correction_store() -> None:
    """ONE_SHOT recording never reads or writes Correction state."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _incomplete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = MagicMock(spec=CorrectionStore)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        cast(CorrectionStore, store),
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="lunch 15 eur",
            source_type="text",
            mode=RecordingMode.ONE_SHOT,
        )
    )

    assert outcome == ExtractionIncomplete(extraction=_incomplete_extraction())
    repository.save.assert_not_called()
    store.get.assert_not_called()
    store.set.assert_not_called()
    store.remove.assert_not_called()


@pytest.mark.parametrize(
    ("source", "source_type", "receipt_photo_id"),
    [
        ("lunch 15 eur", "text", None),
        (b"image bytes", "image", "photo-file-id-123"),
    ],
)
def test_conversational_incomplete_opens_correction(
    source: str | bytes,
    source_type: Literal["image", "text"],
    receipt_photo_id: str | None,
) -> None:
    """Conversational incomplete extraction (text or photo) opens Correction state."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        CorrectionOpened,
        RecordExpense,
        RecordingMode,
    )

    partial = _incomplete_extraction()
    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = partial
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source=source,
            source_type=source_type,
            mode=RecordingMode.CONVERSATIONAL,
            receipt_photo_id=receipt_photo_id,
        )
    )

    assert outcome == CorrectionOpened(extraction=partial)
    extraction.extract.assert_called_once_with(source, source_type)
    extraction.refine.assert_not_called()
    repository.save.assert_not_called()
    pending = store.get(12345)
    assert pending is not None
    assert pending.user_id == 12345
    assert pending.original_result is partial
    assert pending.attempt_count == 1


def test_correction_resolve_saves_clears_and_returns_resolved() -> None:
    """Pending Correction + complete refine -> Expense saved, state cleared, resolved."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        CorrectionResolved,
        RecordExpense,
        RecordingMode,
    )

    original = _incomplete_extraction()
    refined = _complete_extraction()
    extraction = MagicMock(spec=ExtractionPort)
    extraction.refine.return_value = refined
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = lambda expense: replace(expense, id=43)
    store = CorrectionStore()
    store.set(
        12345,
        PendingCorrection(user_id=12345, original_result=original, attempt_count=1),
    )
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    with patch("expense_report.application.expense_recording.datetime") as clock:
        clock.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
        outcome = use_case.record(
            RecordExpense(
                user_id=12345,
                source="Restaurant EUR 15 on 2026-07-15",
                source_type="text",
                mode=RecordingMode.CONVERSATIONAL,
            )
        )

    assert isinstance(outcome, CorrectionResolved)
    assert outcome.extraction == refined
    assert outcome.expense.id == 43
    # refine receives the ORIGINAL partial result and the raw correction text
    extraction.refine.assert_called_once_with(original, "Restaurant EUR 15 on 2026-07-15")
    extraction.extract.assert_not_called()
    assert store.get(12345) is None

    # Verify every field of the Expense passed to repository.save
    saved_expense: Expense = repository.save.call_args.args[0]
    assert saved_expense.id is None  # assigned by repository
    assert saved_expense.amount == Decimal("15.00")
    assert saved_expense.currency == "EUR"
    assert saved_expense.merchant == "Restaurant"
    assert saved_expense.date == date(2026, 7, 15)
    assert saved_expense.category == "food"
    assert saved_expense.user_id == 12345
    # Pinned quirk: receipt_photo_id is None on Correction saves, even when the
    # original partial Extraction came from a photo.
    assert saved_expense.receipt_photo_id is None
    assert saved_expense.created_at == datetime(2026, 7, 20, 14, 0, 0)


@pytest.mark.parametrize("attempt_count", [1, 2])
def test_correction_still_incomplete_increments_attempt(attempt_count: int) -> None:
    """Refined but still incomplete -> attempt increments (1->2, 2->3), original kept."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        CorrectionStillIncomplete,
        RecordExpense,
        RecordingMode,
    )

    original = _incomplete_extraction()
    refined = ExtractionResult(
        amount=Decimal("15.00"),
        currency="EUR",
        merchant=None,
        date=None,
        category=None,
    )
    extraction = MagicMock(spec=ExtractionPort)
    extraction.refine.return_value = refined
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    store.set(
        12345,
        PendingCorrection(user_id=12345, original_result=original, attempt_count=attempt_count),
    )
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="it was EUR",
            source_type="text",
            mode=RecordingMode.CONVERSATIONAL,
        )
    )

    assert outcome == CorrectionStillIncomplete(extraction=refined, attempt_count=attempt_count + 1)
    extraction.refine.assert_called_once_with(original, "it was EUR")
    extraction.extract.assert_not_called()
    repository.save.assert_not_called()
    pending = store.get(12345)
    assert pending is not None
    assert pending.attempt_count == attempt_count + 1
    assert pending.original_result is original


def test_correction_maxed_out_returns_limit_reached_without_refining() -> None:
    """Maxed-out pending Correction -> limit reached; no refine, no save, state cleared."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        CorrectionLimitReached,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.refine.return_value = _complete_extraction()  # would complete; never called
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    store.set(
        12345,
        PendingCorrection(user_id=12345, original_result=_incomplete_extraction(), attempt_count=3),
    )
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="final correction",
            source_type="text",
            mode=RecordingMode.CONVERSATIONAL,
        )
    )

    assert outcome == CorrectionLimitReached()
    extraction.refine.assert_not_called()
    extraction.extract.assert_not_called()
    repository.save.assert_not_called()
    assert store.get(12345) is None


def test_complete_image_leaves_stale_pending_untouched() -> None:
    """A complete photo Extraction does not clear a stale pending Correction."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
    )

    stale = PendingCorrection(
        user_id=12345, original_result=_incomplete_extraction(), attempt_count=2
    )
    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = lambda expense: replace(expense, id=44)
    store = CorrectionStore()
    store.set(12345, stale)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source=b"image bytes",
            source_type="image",
            mode=RecordingMode.CONVERSATIONAL,
            receipt_photo_id="photo-file-id-123",
        )
    )

    assert isinstance(outcome, ExpenseRecorded)
    extraction.extract.assert_called_once_with(b"image bytes", "image")
    extraction.refine.assert_not_called()
    pending = store.get(12345)
    assert pending is stale  # untouched: same object, same attempt count
    assert pending is not None and pending.attempt_count == 2


def test_incomplete_image_overwrites_stale_pending() -> None:
    """An incomplete photo Extraction overwrites a stale pending Correction (attempt 1)."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        CorrectionOpened,
        RecordExpense,
        RecordingMode,
    )

    stale_original = ExtractionResult(
        amount=None,
        currency="USD",
        merchant=None,
        date=None,
        category=None,
    )
    new_partial = _incomplete_extraction()
    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = new_partial
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    store.set(
        12345,
        PendingCorrection(user_id=12345, original_result=stale_original, attempt_count=2),
    )
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source=b"image bytes",
            source_type="image",
            mode=RecordingMode.CONVERSATIONAL,
            receipt_photo_id="photo-file-id-123",
        )
    )

    assert outcome == CorrectionOpened(extraction=new_partial)
    extraction.extract.assert_called_once_with(b"image bytes", "image")
    extraction.refine.assert_not_called()
    repository.save.assert_not_called()
    pending = store.get(12345)
    assert pending is not None
    assert pending.original_result is new_partial  # stale state overwritten
    assert pending.attempt_count == 1


def test_extraction_exception_propagates() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.side_effect = RuntimeError("extract failed")
    repository = MagicMock(spec=ExpenseRepositoryPort)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        CorrectionStore(),
    )

    with pytest.raises(RuntimeError, match="extract failed"):
        use_case.record(RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT))


def test_refine_exception_propagates() -> None:
    """A refine() failure propagates and leaves the pending Correction state untouched."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.refine.side_effect = RuntimeError("refine failed")
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    store.set(
        12345,
        PendingCorrection(user_id=12345, original_result=_incomplete_extraction(), attempt_count=1),
    )
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    with pytest.raises(RuntimeError, match="refine failed"):
        use_case.record(RecordExpense(12345, "correction", "text", RecordingMode.CONVERSATIONAL))

    assert store.get(12345) is not None  # pending state untouched by the failure


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
        CorrectionStore(),
    )

    with pytest.raises(RuntimeError, match="save failed"):
        use_case.record(RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT))


@pytest.mark.parametrize("mode_name", ["ONE_SHOT", "CONVERSATIONAL"])
def test_complete_image_records_expense_with_receipt_photo_id(mode_name: str) -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = lambda expense: replace(expense, id=42)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        CorrectionStore(),
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source=b"image bytes",
            source_type="image",
            mode=RecordingMode[mode_name],
            receipt_photo_id="photo-file-id-123",
        )
    )

    assert isinstance(outcome, ExpenseRecorded)
    assert outcome.expense.id == 42
    assert outcome.expense.receipt_photo_id == "photo-file-id-123"
    extraction.extract.assert_called_once_with(b"image bytes", "image")

    # Verify the Expense passed to repository.save carries the Receipt photo ID
    saved_expense: Expense = repository.save.call_args.args[0]
    assert saved_expense.id is None  # assigned by repository
    assert saved_expense.receipt_photo_id == "photo-file-id-123"
    assert saved_expense.user_id == 12345


def test_incomplete_image_one_shot_returns_without_persisting() -> None:
    """ONE_SHOT incomplete image returns ExtractionIncomplete; no state, no save."""
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _incomplete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    store = CorrectionStore()
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
        store,
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source=b"image bytes",
            source_type="image",
            mode=RecordingMode.ONE_SHOT,
        )
    )

    assert outcome == ExtractionIncomplete(extraction=_incomplete_extraction())
    repository.save.assert_not_called()
    assert store.get(12345) is None


def test_use_case_satisfies_expense_recording_port() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import ExpenseRecordingPort

    extraction = MagicMock(spec=ExtractionPort)
    repository = MagicMock(spec=ExpenseRepositoryPort)

    assert isinstance(
        ExpenseRecordingUseCase(
            cast(ExtractionPort, extraction),
            cast(ExpenseRepositoryPort, repository),
            CorrectionStore(),
        ),
        ExpenseRecordingPort,
    )
