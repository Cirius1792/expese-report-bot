"""Tests for correction state management — PendingCorrection and CorrectionStore."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from expense_report.domain.correction_state import CorrectionStore, PendingCorrection
from expense_report.domain.models import ExtractionResult


class TestPendingCorrection:
    """Tests for PendingCorrection dataclass."""

    def test_creation_with_default_attempt(self) -> None:
        """PendingCorrection defaults to attempt_count=1."""
        result = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=12345, original_result=result)
        assert pc.user_id == 12345
        assert pc.original_result is result
        assert pc.attempt_count == 1

    def test_creation_with_custom_attempt(self) -> None:
        """PendingCorrection accepts custom attempt_count."""
        result = ExtractionResult(
            amount=None, currency=None, merchant=None, date=None, category=None,
        )
        pc = PendingCorrection(
            user_id=12345, original_result=result, attempt_count=2
        )
        assert pc.attempt_count == 2

    def test_maxed_out_false_at_1_attempt(self) -> None:
        """maxed_out is False when attempt_count < 3."""
        result = ExtractionResult(
            amount=None, currency=None, merchant=None, date=None, category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=1)
        assert pc.maxed_out is False

    def test_maxed_out_false_at_2_attempts(self) -> None:
        """maxed_out is False when attempt_count == 2."""
        result = ExtractionResult(
            amount=None, currency=None, merchant=None, date=None, category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=2)
        assert pc.maxed_out is False

    def test_maxed_out_true_at_3_attempts(self) -> None:
        """maxed_out is True when attempt_count >= 3."""
        result = ExtractionResult(
            amount=None, currency=None, merchant=None, date=None, category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=3)
        assert pc.maxed_out is True

    def test_maxed_out_true_above_3(self) -> None:
        """maxed_out is True when attempt_count > 3."""
        result = ExtractionResult(
            amount=None, currency=None, merchant=None, date=None, category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=5)
        assert pc.maxed_out is True


class TestCorrectionStore:
    """Tests for CorrectionStore in-memory store."""

    def test_set_and_get(self) -> None:
        """set stores a correction, get retrieves it."""
        store = CorrectionStore()
        result = ExtractionResult(
            amount=Decimal("10.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=42, original_result=result)
        store.set(42, pc)
        retrieved = store.get(42)
        assert retrieved is not None
        assert retrieved.user_id == 42
        assert retrieved.original_result is result

    def test_get_returns_none_for_unknown_user(self) -> None:
        """get returns None when no correction exists for user."""
        store = CorrectionStore()
        result = store.get(99999)
        assert result is None

    def test_get_returns_none_for_never_set(self) -> None:
        """get returns None for a user never added to the store."""
        store = CorrectionStore()
        assert store.get(0) is None

    def test_remove_clears_entry(self) -> None:
        """remove deletes an existing entry from the store."""
        store = CorrectionStore()
        result = ExtractionResult(
            amount=Decimal("10.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=42, original_result=result)
        store.set(42, pc)
        store.remove(42)
        assert store.get(42) is None

    def test_remove_unknown_user_does_nothing(self) -> None:
        """remove on a non-existent entry does not raise."""
        store = CorrectionStore()
        store.remove(99999)  # Should not raise

    def test_set_overwrites_existing(self) -> None:
        """set overwrites a previous pending correction for the same user."""
        store = CorrectionStore()
        result1 = ExtractionResult(
            amount=Decimal("10.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        result2 = ExtractionResult(
            amount=None,
            currency="EUR",
            merchant=None,
            date=None,
            category=None,
        )
        store.set(42, PendingCorrection(user_id=42, original_result=result1))
        store.set(42, PendingCorrection(user_id=42, original_result=result2))
        retrieved = store.get(42)
        assert retrieved is not None
        assert retrieved.original_result is result2
