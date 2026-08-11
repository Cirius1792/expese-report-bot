"""Tests for PendingCorrection domain entity."""

from __future__ import annotations

from decimal import Decimal

from expense_report.domain.correction_state import PendingCorrection
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
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=12345, original_result=result, attempt_count=2)
        assert pc.attempt_count == 2

    def test_maxed_out_false_at_1_attempt(self) -> None:
        """maxed_out is False when attempt_count < 3."""
        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=1)
        assert pc.maxed_out is False

    def test_maxed_out_false_at_2_attempts(self) -> None:
        """maxed_out is False when attempt_count == 2."""
        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=2)
        assert pc.maxed_out is False

    def test_maxed_out_true_at_3_attempts(self) -> None:
        """maxed_out is True when attempt_count >= 3."""
        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=3)
        assert pc.maxed_out is True

    def test_maxed_out_true_above_3(self) -> None:
        """maxed_out is True when attempt_count > 3."""
        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        pc = PendingCorrection(user_id=1, original_result=result, attempt_count=5)
        assert pc.maxed_out is True
