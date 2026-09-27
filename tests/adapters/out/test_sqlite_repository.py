"""Tests for SqliteExpenseRepository using in-memory SQLite."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

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
        """When expense.id is None, save assigns an auto-increment integer id."""
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
        assert isinstance(saved.id, int)
        assert saved.id >= 1

    def test_save_preserves_id_when_set(self, repo: "SqliteExpenseRepository") -> None:
        """When expense.id is set, save preserves it."""
        expense = Expense(
            id=99,
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

        assert saved.id == 99


class TestGetById:
    """Retrieve by id."""

    def test_get_by_id_returns_none_for_unknown(self, repo: "SqliteExpenseRepository") -> None:
        """Unknown id returns None."""
        result = repo.get_by_id(99999)
        assert result is None

    def test_get_by_id_returns_saved_expense(self, repo: "SqliteExpenseRepository") -> None:
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
        assert saved.id is not None
        retrieved = repo.get_by_id(saved.id)

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

    def test_returns_ordered_by_created_at_desc(self, repo: "SqliteExpenseRepository") -> None:
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

    def test_returns_empty_list_for_no_results(self, repo: "SqliteExpenseRepository") -> None:
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
        assert saved.id is not None
        retrieved = repo.get_by_id(saved.id)

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
        assert saved.id is not None
        retrieved = repo.get_by_id(saved.id)

        assert retrieved is not None
        assert retrieved.category is None

    def test_receipt_photo_id_none_round_trip(self, repo: "SqliteExpenseRepository") -> None:
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
        assert saved.id is not None
        retrieved = repo.get_by_id(saved.id)

        assert retrieved is not None
        assert retrieved.receipt_photo_id is None

    def test_satisfies_repository_port(self, repo: "SqliteExpenseRepository") -> None:
        """SqliteExpenseRepository is recognized as an ExpenseRepositoryPort."""
        from expense_report.ports.repository import ExpenseRepositoryPort

        assert isinstance(repo, ExpenseRepositoryPort)


class TestGetMonthsWithExpenses:
    """Tests for get_months_with_expenses query."""

    def test_returns_months_with_expenses(self) -> None:
        """Queries across a year and returns only months that have expenses."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        user_id = 12345

        # Seed: July (2 expenses), March (1 expense), no other months
        for expense_date, merchant in [
            ("2026-07-10", "Shop A"),
            ("2026-07-20", "Shop B"),
            ("2026-03-05", "Shop C"),
        ]:
            repo.save(
                Expense(
                    id=None,
                    amount=Decimal("10.00"),
                    currency="EUR",
                    merchant=merchant,
                    date=date.fromisoformat(expense_date),
                    category=None,
                    user_id=user_id,
                    receipt_photo_id=None,
                    created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
                )
            )

        result = repo.get_months_with_expenses(user_id, 2026)
        assert result == {3, 7}

    def test_returns_empty_set_when_no_expenses(self) -> None:
        """Returns empty set for a user with no expenses in that year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        result = repo.get_months_with_expenses(99999, 2026)
        assert result == set()

    def test_multi_user_isolation(self) -> None:
        """Each user sees only their own months."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(
            Expense(
                id=None,
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="A",
                date=date(2026, 7, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 12, 0, 0),
            )
        )
        repo.save(
            Expense(
                id=None,
                amount=Decimal("20.00"),
                currency="EUR",
                merchant="B",
                date=date(2026, 3, 1),
                category=None,
                user_id=456,
                receipt_photo_id=None,
                created_at=datetime(2026, 3, 1, 12, 0, 0),
            )
        )

        assert repo.get_months_with_expenses(123, 2026) == {7}
        assert repo.get_months_with_expenses(456, 2026) == {3}

    def test_different_years_returned_separately(self) -> None:
        """Querying 2025 returns months only from 2025, not 2026."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(
            Expense(
                id=None,
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="A",
                date=date(2026, 7, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 12, 0, 0),
            )
        )
        repo.save(
            Expense(
                id=None,
                amount=Decimal("20.00"),
                currency="EUR",
                merchant="B",
                date=date(2025, 12, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2025, 12, 1, 12, 0, 0),
            )
        )

        assert repo.get_months_with_expenses(123, 2025) == {12}
        assert repo.get_months_with_expenses(123, 2026) == {7}


class TestDeleteById:
    """Tests for delete_by_id with user scoping."""

    def _create_expense(
        self,
        repo: "SqliteExpenseRepository",
        user_id: int,
        d: date,
        amount: str = "10.00",
        currency: str = "EUR",
        merchant: str = "Shop",
    ) -> Expense:
        return repo.save(
            Expense(
                id=None,
                amount=Decimal(amount),
                currency=currency,
                merchant=merchant,
                date=d,
                category=None,
                user_id=user_id,
                receipt_photo_id=None,
                created_at=datetime(d.year, d.month, d.day, 12, 0, 0),
            )
        )

    def test_delete_by_id_removes_and_returns_expense(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """delete_by_id removes the expense and returns the deleted data."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 10), amount="42.50")

        assert saved.id is not None
        result = repo.delete_by_id(user_id=1, expense_id=saved.id)

        assert result is not None
        assert result.id == saved.id
        assert result.amount == Decimal("42.50")

        # Verify hard delete: not retrievable
        assert repo.get_by_id(saved.id) is None

    def test_delete_by_id_returns_none_when_not_found(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """delete_by_id returns None for a non-existent id."""
        result = repo.delete_by_id(user_id=1, expense_id=99999)
        assert result is None

    def test_delete_by_id_scoped_to_user(self, repo: "SqliteExpenseRepository") -> None:
        """delete_by_id only deletes if user_id matches, returns None otherwise."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 10))

        # User 2 tries to delete user 1's expense
        assert saved.id is not None
        result = repo.delete_by_id(user_id=2, expense_id=saved.id)
        assert result is None

        # User 1's expense still exists
        assert repo.get_by_id(saved.id) is not None

    def test_delete_by_id_scoped_to_user_succeeds_for_owner(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """delete_by_id succeeds when user_id matches the owner."""
        saved = self._create_expense(repo, user_id=42, d=date(2026, 7, 10))
        assert saved.id is not None
        result = repo.delete_by_id(user_id=42, expense_id=saved.id)
        assert result is not None
        assert repo.get_by_id(saved.id) is None


class TestGetTotalByUserAndYear:
    """Tests for get_total_by_user_and_year query."""

    def test_sums_all_expenses_in_year(self) -> None:
        """Returns the sum of all expense amounts for a user in a year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        user_id = 12345

        for expense_date, amount in [
            ("2026-07-10", "42.50"),
            ("2026-07-20", "12.50"),
            ("2026-03-05", "30.00"),
        ]:
            repo.save(
                Expense(
                    id=None,
                    amount=Decimal(amount),
                    currency="EUR",
                    merchant="Shop",
                    date=date.fromisoformat(expense_date),
                    category=None,
                    user_id=user_id,
                    receipt_photo_id=None,
                    created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
                )
            )

        result = repo.get_total_by_user_and_year(user_id, 2026)
        assert result == Decimal("85.00")

    def test_returns_zero_when_no_expenses(self) -> None:
        """Returns Decimal 0.00 when no expenses exist for the user/year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        result = repo.get_total_by_user_and_year(99999, 2026)
        assert result == Decimal("0.00")

    def test_multi_user_isolation(self) -> None:
        """Each user's total is independent."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(
            Expense(
                id=None,
                amount=Decimal("50.00"),
                currency="EUR",
                merchant="A",
                date=date(2026, 7, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 12, 0, 0),
            )
        )
        repo.save(
            Expense(
                id=None,
                amount=Decimal("30.00"),
                currency="EUR",
                merchant="B",
                date=date(2026, 7, 2),
                category=None,
                user_id=456,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 2, 12, 0, 0),
            )
        )

        assert repo.get_total_by_user_and_year(123, 2026) == Decimal("50.00")
        assert repo.get_total_by_user_and_year(456, 2026) == Decimal("30.00")

    def test_only_sums_requested_year(self) -> None:
        """Only sums expenses from the specified year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(
            Expense(
                id=None,
                amount=Decimal("100.00"),
                currency="EUR",
                merchant="A",
                date=date(2026, 7, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 12, 0, 0),
            )
        )
        repo.save(
            Expense(
                id=None,
                amount=Decimal("50.00"),
                currency="EUR",
                merchant="B",
                date=date(2025, 12, 1),
                category=None,
                user_id=123,
                receipt_photo_id=None,
                created_at=datetime(2025, 12, 1, 12, 0, 0),
            )
        )

        assert repo.get_total_by_user_and_year(123, 2026) == Decimal("100.00")

    def test_handles_floating_point_sensitive_values(self) -> None:
        """Sums like 0.10 + 0.20 return exact 0.30, not floating-point error."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        for expense_date, amount in [
            ("2026-07-01", "0.10"),
            ("2026-07-02", "0.20"),
        ]:
            repo.save(
                Expense(
                    id=None,
                    amount=Decimal(amount),
                    currency="EUR",
                    merchant="Shop",
                    date=date.fromisoformat(expense_date),
                    category=None,
                    user_id=12345,
                    receipt_photo_id=None,
                    created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
                )
            )

        result = repo.get_total_by_user_and_year(12345, 2026)
        assert result == Decimal("0.30")


class TestLogicalDeletion:
    """Logical deletion (ADR 0011) — deleted_at timestamp + include_deleted opt-in."""

    def _create_expense(
        self,
        repo: "SqliteExpenseRepository",
        user_id: int,
        d: date,
        amount: str = "10.00",
        merchant: str = "Shop",
    ) -> Expense:
        return repo.save(
            Expense(
                id=None,
                amount=Decimal(amount),
                currency="EUR",
                merchant=merchant,
                date=d,
                category=None,
                user_id=user_id,
                receipt_photo_id=None,
                created_at=datetime(d.year, d.month, d.day, 12, 0, 0),
            )
        )

    def test_save_leaves_deleted_at_none(self, repo: "SqliteExpenseRepository") -> None:
        """Saving a new expense leaves deleted_at as None."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        assert saved.deleted_at is None

    def test_delete_by_id_soft_deletes_row_retained(self, repo: "SqliteExpenseRepository") -> None:
        """delete_by_id sets deleted_at and retains the row in the table."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 1), amount="42.50")
        assert saved.id is not None

        result = repo.delete_by_id(user_id=1, expense_id=saved.id)

        # Caller still gets the deleted expense for the success message.
        assert result is not None
        assert result.id == saved.id
        assert result.amount == Decimal("42.50")

        # The row is retained in the table with deleted_at set.
        row = repo._conn.execute(
            "SELECT deleted_at FROM expenses WHERE id = ?", (saved.id,)
        ).fetchone()
        assert row is not None
        assert row["deleted_at"] is not None

    def test_get_by_id_filters_deleted_by_default(self, repo: "SqliteExpenseRepository") -> None:
        """get_by_id excludes soft-deleted rows by default."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        assert saved.id is not None
        repo.delete_by_id(user_id=1, expense_id=saved.id)

        assert repo.get_by_id(saved.id) is None

    def test_get_by_id_include_deleted_returns_deleted(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """get_by_id(include_deleted=True) returns soft-deleted rows."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        assert saved.id is not None
        repo.delete_by_id(user_id=1, expense_id=saved.id)

        retrieved = repo.get_by_id(saved.id, include_deleted=True)

        assert retrieved is not None
        assert retrieved.id == saved.id
        assert retrieved.deleted_at is not None

    def test_get_by_user_and_month_filters_deleted_by_default(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """get_by_user_and_month excludes soft-deleted rows by default."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1), merchant="Live")
        gone = self._create_expense(repo, user_id=1, d=date(2026, 7, 2), merchant="Gone")
        assert gone.id is not None
        repo.delete_by_id(user_id=1, expense_id=gone.id)

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7)

        assert [e.merchant for e in results] == ["Live"]

    def test_get_by_user_and_month_include_deleted_returns_all(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """include_deleted=True returns live and soft-deleted rows alike."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1), merchant="Live")
        gone = self._create_expense(repo, user_id=1, d=date(2026, 7, 2), merchant="Gone")
        assert gone.id is not None
        repo.delete_by_id(user_id=1, expense_id=gone.id)

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=7, include_deleted=True)

        assert {e.merchant for e in results} == {"Live", "Gone"}

    def test_get_months_with_expenses_excludes_deleted(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """Month discovery excludes months whose only expenses are soft-deleted."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        gone = self._create_expense(repo, user_id=1, d=date(2026, 3, 5))
        assert gone.id is not None
        repo.delete_by_id(user_id=1, expense_id=gone.id)

        assert repo.get_months_with_expenses(1, 2026) == {7}

    def test_get_total_by_user_and_year_excludes_deleted(
        self, repo: "SqliteExpenseRepository"
    ) -> None:
        """Year totals exclude soft-deleted expenses."""
        self._create_expense(repo, user_id=1, d=date(2026, 7, 1), amount="40.00")
        gone = self._create_expense(repo, user_id=1, d=date(2026, 3, 5), amount="30.00")
        assert gone.id is not None
        repo.delete_by_id(user_id=1, expense_id=gone.id)

        assert repo.get_total_by_user_and_year(1, 2026) == Decimal("40.00")

    def test_delete_already_deleted_returns_none(self, repo: "SqliteExpenseRepository") -> None:
        """Deleting an already soft-deleted expense returns None (not found)."""
        saved = self._create_expense(repo, user_id=1, d=date(2026, 7, 1))
        assert saved.id is not None
        repo.delete_by_id(user_id=1, expense_id=saved.id)

        assert repo.delete_by_id(user_id=1, expense_id=saved.id) is None

    def test_soft_delete_does_not_disturb_siblings(self, repo: "SqliteExpenseRepository") -> None:
        """Soft-deleting one expense leaves sibling rows untouched (ids stable)."""
        e1 = self._create_expense(repo, user_id=1, d=date(2026, 7, 1), merchant="A")
        e2 = self._create_expense(repo, user_id=1, d=date(2026, 7, 2), merchant="B")
        e3 = self._create_expense(repo, user_id=1, d=date(2026, 7, 3), merchant="C")
        assert e1.id is not None and e2.id is not None and e3.id is not None

        repo.delete_by_id(user_id=1, expense_id=e2.id)

        # Newest-first ordering: e3 (Jul 3), then e1 (Jul 1); e2 is gone.
        remaining = repo.get_by_user_and_month(user_id=1, year=2026, month=7)
        assert [e.id for e in remaining] == [e3.id, e1.id]
        assert repo.get_by_id(e2.id, include_deleted=True) is not None


class TestSchemaMigration:
    """Schema migration for pre-existing databases (no deleted_at column)."""

    def test_existing_db_without_deleted_at_migrates(self, tmp_path) -> None:
        """A DB created with the old schema gains deleted_at; rows read as live."""
        import sqlite3

        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        db_file = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_file)
        conn.execute(
            """
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                merchant TEXT NOT NULL,
                date TEXT NOT NULL,
                category TEXT,
                user_id INTEGER NOT NULL,
                receipt_photo_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO expenses"
            " (amount, currency, merchant, date, category, user_id, receipt_photo_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("10.00", "EUR", "Legacy Shop", "2026-07-01", None, 42, None, "2026-07-01T12:00:00"),
        )
        conn.commit()
        conn.close()

        repo = SqliteExpenseRepository(str(db_file))

        cols = {row[1] for row in repo._conn.execute("PRAGMA table_info(expenses)").fetchall()}
        assert "deleted_at" in cols

        expenses = repo.get_by_user_and_month(user_id=42, year=2026, month=7)
        assert len(expenses) == 1
        assert expenses[0].merchant == "Legacy Shop"
        assert expenses[0].deleted_at is None
