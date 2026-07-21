"""SQLite implementation of the ExpenseRepositoryPort.

Uses the sqlite3 module with check_same_thread=False for single-container use.
Thread safety is the caller's responsibility.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from decimal import Decimal

from expense_report.domain.models import Expense

logger = logging.getLogger(__name__)


class SqliteExpenseRepository:
    """Persists and retrieves Expense records using SQLite.

    Args:
        db_path: Path to the SQLite database file. Use ':memory:' for tests.
    """

    def __init__(self, db_path: str) -> None:
        logger.info("Initializing SQLite repository at %s", db_path)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self) -> None:
        """Create the expenses table if it doesn't exist."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
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
        self._conn.commit()

    def save(self, expense: Expense) -> Expense:
        """Persist an expense record.

        If expense.id is None, SQLite assigns an auto-increment integer id.
        If expense.id is set, it is used as-is (INSERT with explicit id).
        """
        if expense.id is not None:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO expenses
                    (id, amount, currency, merchant, date, category,
                     user_id, receipt_photo_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense.id,
                    str(expense.amount),
                    expense.currency,
                    expense.merchant,
                    expense.date.isoformat(),
                    expense.category,
                    expense.user_id,
                    expense.receipt_photo_id,
                    expense.created_at.isoformat(),
                ),
            )
            self._conn.commit()
            logger.info("Saved expense %s for user %s", expense.id, expense.user_id)
            return Expense(
                id=expense.id,
                amount=expense.amount,
                currency=expense.currency,
                merchant=expense.merchant,
                date=expense.date,
                category=expense.category,
                user_id=expense.user_id,
                receipt_photo_id=expense.receipt_photo_id,
                created_at=expense.created_at,
            )
        else:
            cursor = self._conn.execute(
                """
                INSERT INTO expenses
                    (amount, currency, merchant, date, category,
                     user_id, receipt_photo_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(expense.amount),
                    expense.currency,
                    expense.merchant,
                    expense.date.isoformat(),
                    expense.category,
                    expense.user_id,
                    expense.receipt_photo_id,
                    expense.created_at.isoformat(),
                ),
            )
            self._conn.commit()
            new_id = cursor.lastrowid
            logger.info("Saved expense %s for user %s", new_id, expense.user_id)
            return Expense(
                id=new_id,
                amount=expense.amount,
                currency=expense.currency,
                merchant=expense.merchant,
                date=expense.date,
                category=expense.category,
                user_id=expense.user_id,
                receipt_photo_id=expense.receipt_photo_id,
                created_at=expense.created_at,
            )

    def get_by_id(self, expense_id: int) -> Expense | None:
        """Retrieve a single expense by its unique identifier."""
        row = self._conn.execute(
            "SELECT * FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()

        if row is None:
            logger.info("Expense %s not found", expense_id)
            return None

        logger.info("Retrieved expense %s", expense_id)
        return self._row_to_expense(row)

    def get_by_user_and_month(
        self,
        user_id: int,
        year: int,
        month: int,
    ) -> list[Expense]:
        """Retrieve all expenses for a given user in a given month, newest first."""
        prefix = f"{year:04d}-{month:02d}"
        rows = self._conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date LIKE ? ORDER BY created_at DESC",
            (user_id, f"{prefix}%"),
        ).fetchall()

        expenses = [self._row_to_expense(row) for row in rows]
        logger.info(
            "Retrieved %s expenses for user %s in %04d-%02d",
            len(expenses),
            user_id,
            year,
            month,
        )
        return expenses

    def get_months_with_expenses(self, user_id: int, year: int) -> set[int]:
        """Return the set of month numbers (1-12) that have expenses for a user in a year."""
        prefix = f"{year:04d}-"
        rows = self._conn.execute(
            "SELECT DISTINCT substr(date, 6, 2) AS month FROM expenses"
            " WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{prefix}%"),
        ).fetchall()

        months = {int(row["month"]) for row in rows}
        logger.info(
            "Found %s months with expenses for user %s in %04d",
            len(months),
            user_id,
            year,
        )
        return months

    def get_total_by_user_and_year(self, user_id: int, year: int) -> Decimal:
        """Return the sum of all expense amounts for a user in a year."""
        prefix = f"{year:04d}-"
        rows = self._conn.execute(
            "SELECT amount FROM expenses WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{prefix}%"),
        ).fetchall()

        total = sum(
            (Decimal(row["amount"]) for row in rows),
            start=Decimal("0.00"),
        )
        logger.info(
            "Total for user %s in %04d: %s",
            user_id,
            year,
            total,
        )
        return total

    def delete_by_id(self, user_id: int, expense_id: int) -> Expense | None:
        """Delete an expense by its integer id, scoped to the given user.

        Returns the deleted Expense for the caller to format a success message,
        or None if no matching expense was found.
        """
        row = self._conn.execute(
            "SELECT * FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()

        if row is None:
            logger.info(
                "Expense %s not found for user %s — nothing to delete",
                expense_id,
                user_id,
            )
            return None

        self._conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        )
        self._conn.commit()

        logger.info("Deleted expense %s for user %s", expense_id, user_id)

        return self._row_to_expense(row)

    @staticmethod
    def _row_to_expense(row: sqlite3.Row) -> Expense:
        """Convert a SQLite row to an Expense domain object."""
        return Expense(
            id=int(row["id"]),
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            merchant=row["merchant"],
            date=date.fromisoformat(row["date"]),
            category=row["category"],
            user_id=row["user_id"],
            receipt_photo_id=row["receipt_photo_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
