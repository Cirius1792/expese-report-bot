"""Tests for SqliteExpenseRepository using in-memory SQLite."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from expense_report.domain.models import Expense


@pytest.fixture
def repo() -> "SqliteExpenseRepository":
    """Create a fresh in-memory repository for each test."""
    from expense_report.adapters.out.sqlite_repository import (
        SqliteExpenseRepository,
    )

    return SqliteExpenseRepository(":memory:")


class TestSave:
    """Save logic — id assignment and preservation."""

    def test_save_assigns_id_when_none(self, repo: "SqliteExpenseRepository") -> None:
        """When expense.id is None, save assigns a UUID4 string id."""
        expense = Expense(
            id=None,
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category="food",
            user_id=123,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 1, 12, 0, 0),
        )

        saved = repo.save(expense)

        assert saved.id is not None
        assert isinstance(saved.id, str)
        # UUID4 format: 8-4-4-4-12 hex digits
        assert len(saved.id) == 36

    def test_save_preserves_id_when_set(self, repo: "SqliteExpenseRepository") -> None:
        """When expense.id is set, save preserves it."""
        expense = Expense(
            id="my-custom-id",
            amount=Decimal("15.00"),
            currency="USD",
            merchant="Cafe",
            date=date(2026, 7, 2),
            category=None,
            user_id=456,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 2, 14, 0, 0),
        )

        saved = repo.save(expense)

        assert saved.id == "my-custom-id"


class TestGetById:
    """Retrieve by id."""

    def test_get_by_id_returns_none_for_unknown(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """Unknown id returns None."""
        result = repo.get_by_id("nonexistent-id")
        assert result is None

    def test_get_by_id_returns_saved_expense(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """Saved expense can be retrieved by id with correct fields."""
        dt = datetime(2026, 7, 3, 9, 30, 0)
        expense = Expense(
            id=None,
            amount=Decimal("99.99"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 3),
            category="dining",
            user_id=789,
            receipt_photo_id="photo-abc",
            created_at=dt,
        )

        saved = repo.save(expense)
        retrieved = repo.get_by_id(saved.id)  # type: ignore[arg-type]

        assert retrieved is not None
        assert retrieved.id == saved.id
        assert retrieved.amount == Decimal("99.99")
        assert retrieved.currency == "EUR"
        assert retrieved.merchant == "Restaurant"
        assert retrieved.date == date(2026, 7, 3)
        assert retrieved.category == "dining"
        assert retrieved.user_id == 789
        assert retrieved.receipt_photo_id == "photo-abc"
        assert retrieved.created_at == dt


class TestGetByUserAndMonth:
    """Filter by user and month."""

    def _create_expense(
        self,
        repo: "SqliteExpenseRepository",
        user_id: int,
        d: date,
        amount: str = "10.00",
        currency: str = "EUR",
        merchant: str = "Shop",
        category: str | None = None,
        receipt_photo_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Expense:
        if created_at is None:
            created_at = datetime(d.year, d.month, d.day, 12, 0, 0)
        return repo.save(
            Expense(
                id=None,
                amount=Decimal(amount),
                currency=currency,
                merchant=merchant,
                date=d,
                category=category,
                user_id=user_id,
                receipt_photo_id=receipt_photo_id,
                created_at=created_at,
            )
        )

    def test_filters_by_user_id(self, repo: "SqliteExpenseRepository") -> None:
        """Expenses for other users are excluded."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        self._create_expense(repo, user_id=2, d=date(2026, 7, 1))

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7)

        assert len(results) == 1
        assert results[0].user_id == 1

    def test_filters_by_month(self, repo: "SqliteExpenseRepository") -> None:
        """Expenses in other months are excluded."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 15))
        self._create_expense(repo, user_id=1, d=date(2026, 8, 1))

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7)

        assert len(results) == 1
        assert results[0].date.month == 7

    def test_filters_by_year(self, repo: "SqliteExpenseRepository") -> None:
        """Expenses in other years are excluded."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        self._create_expense(repo, user_id=1, d=date(2025, 7, 1))

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7)

        assert len(results) == 1
        assert results[0].date.year == 2026

    def test_returns_ordered_by_created_at_desc(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """Results are ordered newest first by created_at."""
        self._create_expense(
            repo,
            user_id=1,
            d=date(2026, 7, 1),
            created_at=datetime(2026, 7, 1, 10, 0, 0),
        )
        self._create_expense(
            repo,
            user_id=1,
            d=date(2026, 7, 2),
            created_at=datetime(2026, 7, 2, 10, 0, 0),
        )
        self._create_expense(
            repo,
            user_id=1,
            d=date(2026, 7, 3),
            created_at=datetime(2026, 7, 3, 10, 0, 0),
        )

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7)

        assert len(results) == 3
        assert results[0].created_at > results[1].created_at
        assert results[1].created_at > results[2].created_at

    def test_returns_empty_list_for_no_results(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """No matching expenses returns an empty list."""
        results = repo.get_by_user_and_month(user_id=999, year=2026, month=1)
        assert results == []


class TestSerialization:
    """Decimal round-trip and nullable fields."""

    def test_decimal_round_trip(self, repo: "SqliteExpenseRepository") -> None:
        """Decimal amounts survive save/retrieve without precision loss."""
        expense = Expense(
            id=None,
            amount=Decimal("123.45"),
            currency="EUR",
            merchant="Precise Shop",
            date=date(2026, 7, 10),
            category="shopping",
            user_id=1,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 10, 8, 0, 0),
        )

        saved = repo.save(expense)
        retrieved = repo.get_by_id(saved.id)  # type: ignore[arg-type]

        assert retrieved is not None
        assert retrieved.amount == Decimal("123.45")
        # Ensure it's still a Decimal, not a float
        assert isinstance(retrieved.amount, Decimal)

    def test_category_none_round_trip(self, repo: "SqliteExpenseRepository") -> None:
        """Category=None survives save/retrieve."""
        expense = Expense(
            id=None,
            amount=Decimal("10.00"),
            currency="EUR",
            merchant="No Cat Shop",
            date=date(2026, 7, 15),
            category=None,
            user_id=1,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )

        saved = repo.save(expense)
        retrieved = repo.get_by_id(saved.id)  # type: ignore[arg-type]

        assert retrieved is not None
        assert retrieved.category is None

    def test_receipt_photo_id_none_round_trip(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """receipt_photo_id=None survives save/retrieve."""
        expense = Expense(
            id=None,
            amount=Decimal("25.00"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 20),
            category="utilities",
            user_id=2,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 20, 16, 0, 0),
        )

        saved = repo.save(expense)
        retrieved = repo.get_by_id(saved.id)  # type: ignore[arg-type]

        assert retrieved is not None
        assert retrieved.receipt_photo_id is None

    def test_satisfies_repository_port(self, repo: "SqliteExpenseRepository") -> None:
        """SqliteExpenseRepository is recognized as an ExpenseRepositoryPort."""
        from expense_report.ports.repository import ExpenseRepositoryPort

        assert isinstance(repo, ExpenseRepositoryPort)
