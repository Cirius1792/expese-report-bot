"""Tests for domain models — Expense and ExtractionResult."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from expense_report.domain.models import Expense, ExtractionResult


class TestExpense:
    """Expense is a frozen dataclass — test creation and immutability."""

    def test_create_with_all_fields(self) -> None:
        """Expense can be created with all fields populated."""
        dt = datetime(2026, 7, 1, 12, 30, 0)
        exp = Expense(
            id="exp-001",
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Grocery Store",
            date=date(2026, 7, 1),
            category="food",
            user_id=123456789,
            receipt_photo_id="AgADBAADFak4Gz9y",
            created_at=dt,
        )
        assert exp.id == "exp-001"
        assert exp.amount == Decimal("42.50")
        assert exp.currency == "EUR"
        assert exp.merchant == "Grocery Store"
        assert exp.date == date(2026, 7, 1)
        assert exp.category == "food"
        assert exp.user_id == 123456789
        assert exp.receipt_photo_id == "AgADBAADFak4Gz9y"
        assert exp.created_at == dt

    def test_create_with_nulls(self) -> None:
        """Expense allows None for id, category, and receipt_photo_id."""
        dt = datetime(2026, 7, 1, 12, 30, 0)
        exp = Expense(
            id=None,
            amount=Decimal("15.00"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 1),
            category=None,
            user_id=987654321,
            receipt_photo_id=None,
            created_at=dt,
        )
        assert exp.id is None
        assert exp.category is None
        assert exp.receipt_photo_id is None

    def test_is_frozen(self) -> None:
        """Expense instances cannot be mutated."""
        dt = datetime(2026, 7, 1, 12, 30, 0)
        exp = Expense(
            id="exp-001",
            amount=Decimal("10.00"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category=None,
            user_id=1,
            receipt_photo_id=None,
            created_at=dt,
        )
        with pytest.raises(AttributeError):
            exp.amount = Decimal("20.00")  # type: ignore[misc]  # ty: ignore[invalid-assignment]


class TestExtractionResult:
    """ExtractionResult completeness logic."""

    def test_is_complete_when_all_mandatory_present(self) -> None:
        """is_complete returns True when amount, currency, merchant, date are present."""
        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 1),
            category="food",
        )
        assert result.is_complete is True

    def test_is_complete_when_amount_none(self) -> None:
        """is_complete returns False when amount is None."""
        result = ExtractionResult(
            amount=None,
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 1),
            category="food",
        )
        assert result.is_complete is False

    def test_is_complete_when_currency_none(self) -> None:
        """is_complete returns False when currency is None."""
        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency=None,
            merchant="Restaurant",
            date=date(2026, 7, 1),
            category="food",
        )
        assert result.is_complete is False

    def test_is_complete_when_merchant_none(self) -> None:
        """is_complete returns False when merchant is None."""
        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency="EUR",
            merchant=None,
            date=date(2026, 7, 1),
            category="food",
        )
        assert result.is_complete is False

    def test_is_complete_when_date_none(self) -> None:
        """is_complete returns False when date is None."""
        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency="EUR",
            merchant="Restaurant",
            date=None,
            category="food",
        )
        assert result.is_complete is False

    def test_is_complete_when_category_none(self) -> None:
        """is_complete returns True when category is None (optional field)."""
        result = ExtractionResult(
            amount=Decimal("29.99"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 1),
            category=None,
        )
        assert result.is_complete is True

    def test_is_complete_when_all_mandatory_none(self) -> None:
        """is_complete returns False when all mandatory fields are None."""
        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        assert result.is_complete is False
