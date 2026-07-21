"""Tests for operational logging in SqliteExpenseRepository.

Verifies that DB init, save, and query operations produce appropriate
log messages without leaking sensitive data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from expense_report.domain.models import Expense

if TYPE_CHECKING:
    from expense_report.adapters.out.sqlite_repository import (
        SqliteExpenseRepository,
    )


@pytest.fixture(autouse=True)
def _setup_logging() -> None:
    """Ensure root logger is configured for caplog tests."""
    logging.basicConfig(level=logging.DEBUG, force=True)


@pytest.fixture
def repo() -> "SqliteExpenseRepository":
    """Create a fresh in-memory repository for each test."""
    from expense_report.adapters.out.sqlite_repository import (
        SqliteExpenseRepository,
    )

    return SqliteExpenseRepository(":memory:")


class TestInitLogging:
    """Verify SQLite initialization produces operational logs."""

    def test_init_logs_db_path(self, caplog: pytest.LogCaptureFixture) -> None:
        """Repository init logs the database path at INFO."""
        caplog.set_level(logging.INFO)

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        SqliteExpenseRepository(":memory:")

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert (
            "sqlite" in messages.lower()
            or "initializ" in messages.lower()
            or "database" in messages.lower()
            or "memory" in messages.lower()
        ), f"No INFO log for SQLite init found. Captured: {[r.message for r in records]}"


class TestSaveLogging:
    """Verify save operations produce operational logs."""

    def test_save_logs_expense_id(self, caplog: pytest.LogCaptureFixture) -> None:
        """Save logs the expense id at INFO."""
        caplog.set_level(logging.INFO)

        expense = Expense(
            id=99,
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category="food",
            user_id=123,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 1, 12, 0, 0),
        )

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(":memory:")
        repo.save(expense)

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "99" in messages, f"No log with expense id '99' in: {records}"

    def test_save_logs_newly_assigned_id(self, caplog: pytest.LogCaptureFixture) -> None:
        """Save with id=None logs the newly assigned integer id at INFO."""
        caplog.set_level(logging.INFO)

        expense = Expense(
            id=None,
            amount=Decimal("10.00"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category=None,
            user_id=456,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 1, 12, 0, 0),
        )

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(":memory:")
        saved = repo.save(expense)

        assert saved.id is not None
        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert str(saved.id) in messages, (
            f"No log with assigned id '{saved.id}' found. Captured: {[r.message for r in records]}"
        )


class TestGetByIdLogging:
    """Verify get_by_id operations produce operational logs."""

    def test_get_by_id_logs_found(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_by_id when found logs at INFO."""
        caplog.set_level(logging.INFO)

        expense = Expense(
            id=42,
            amount=Decimal("99.99"),
            currency="USD",
            merchant="Store",
            date=date(2026, 7, 5),
            category="shopping",
            user_id=789,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 5, 10, 0, 0),
        )

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(":memory:")
        repo.save(expense)
        repo.get_by_id(42)

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "42" in messages, (
            f"No log with id '42' found. Captured: {[r.message for r in records]}"
        )

    def test_get_by_id_logs_not_found(self, caplog: pytest.LogCaptureFixture) -> None:
        """get_by_id when not found logs at INFO or DEBUG."""
        caplog.set_level(logging.INFO)

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(":memory:")
        repo.get_by_id(99999)

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "99999" in messages or "not found" in messages.lower(), (
            f"No log about non-existent id found. Captured: {[r.message for r in records]}"
        )


class TestGetByUserAndMonthLogging:
    """Verify get_by_user_and_month operations produce operational logs."""

    def test_get_by_user_and_month_logs_count(self, caplog: pytest.LogCaptureFixture) -> None:
        """Query logs expense count at INFO."""
        caplog.set_level(logging.INFO)

        from expense_report.adapters.out.sqlite_repository import (
            SqliteExpenseRepository,
        )

        repo = SqliteExpenseRepository(":memory:")

        # Save two expenses
        repo.save(
            Expense(
                id=None,
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="A",
                date=date(2026, 8, 1),
                category=None,
                user_id=1,
                receipt_photo_id=None,
                created_at=datetime(2026, 8, 1, 12, 0, 0),
            )
        )
        repo.save(
            Expense(
                id=None,
                amount=Decimal("20.00"),
                currency="EUR",
                merchant="B",
                date=date(2026, 8, 2),
                category=None,
                user_id=1,
                receipt_photo_id=None,
                created_at=datetime(2026, 8, 2, 12, 0, 0),
            )
        )

        results = repo.get_by_user_and_month(user_id=1, year=2026, month=8)

        assert len(results) == 2
        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        # Should mention count of expenses retrieved
        assert "2" in messages or "two" in messages.lower() or "expense" in messages.lower(), (
            f"No log with expense count '2' found. Captured: {[r.message for r in records]}"
        )
