"""Tests for CorrectionStore — application-owned session state."""

from __future__ import annotations

from expense_report.application.correction_state import CorrectionStore
from expense_report.domain.correction_state import PendingCorrection
from expense_report.domain.models import ExtractionResult


class TestCorrectionStore:
    """Tests for CorrectionStore in-memory store."""

    def test_set_and_get_stores_and_retrieves_correction(self) -> None:
        store = CorrectionStore()
        result = ExtractionResult(
            amount=None,
            currency="EUR",
            merchant=None,
            date=None,
            category=None,
        )
        pending = PendingCorrection(
            user_id=12345,
            original_result=result,
            attempt_count=2,
        )
        store.set(12345, pending)
        retrieved = store.get(12345)
        assert retrieved is not None
        assert retrieved.user_id == 12345
        assert retrieved.original_result == result
        assert retrieved.attempt_count == 2

    def test_get_returns_none_for_unknown_user(self) -> None:
        store = CorrectionStore()
        assert store.get(99999) is None

    def test_set_overwrites_existing_correction(self) -> None:
        store = CorrectionStore()
        result1 = ExtractionResult(
            amount=None, currency="EUR", merchant=None, date=None, category=None
        )
        store.set(12345, PendingCorrection(user_id=12345, original_result=result1))
        result2 = ExtractionResult(
            amount=None, currency="USD", merchant=None, date=None, category=None
        )
        store.set(12345, PendingCorrection(user_id=12345, original_result=result2, attempt_count=3))
        retrieved = store.get(12345)
        assert retrieved is not None
        assert retrieved.original_result == result2
        assert retrieved.attempt_count == 3

    def test_remove_deletes_existing_correction(self) -> None:
        store = CorrectionStore()
        result = ExtractionResult(
            amount=None, currency="EUR", merchant=None, date=None, category=None
        )
        store.set(12345, PendingCorrection(user_id=12345, original_result=result))
        store.remove(12345)
        assert store.get(12345) is None

    def test_remove_does_nothing_for_unknown_user(self) -> None:
        store = CorrectionStore()
        store.remove(99999)  # should not raise
        assert store.get(99999) is None

    def test_store_is_isolated_by_user_id(self) -> None:
        store = CorrectionStore()
        result1 = ExtractionResult(
            amount=None, currency="EUR", merchant=None, date=None, category=None
        )
        result2 = ExtractionResult(
            amount=None, currency="USD", merchant=None, date=None, category=None
        )
        store.set(1, PendingCorrection(user_id=1, original_result=result1))
        store.set(2, PendingCorrection(user_id=2, original_result=result2))
        c1 = store.get(1)
        c2 = store.get(2)
        assert c1 is not None
        assert c2 is not None
        assert c1.original_result == result1
        assert c2.original_result == result2
