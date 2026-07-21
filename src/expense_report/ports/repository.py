"""Port interface for expense repository storage."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from expense_report.domain.models import Expense


@runtime_checkable
class ExpenseRepositoryPort(Protocol):
    """Protocol for persisting and retrieving Expense records."""

    def save(self, expense: Expense) -> Expense:
        """Persist an expense record.

        Args:
            expense: The expense to save (may have id=None for new records).

        Returns:
            The saved expense with a persistent id assigned.
        """
        ...

    def get_by_id(self, expense_id: int) -> Expense | None:
        """Retrieve a single expense by its unique identifier.

        Args:
            expense_id: The persistent integer id of the expense.

        Returns:
            The expense if found, None otherwise.
        """
        ...

    def delete_by_id(self, user_id: int, expense_id: int) -> Expense | None:
        """Delete an expense by its id, scoped to a user.

        Args:
            user_id: The Telegram user id.
            expense_id: The persistent integer id of the expense.

        Returns:
            The deleted Expense if found and deleted, None if not found.
        """
        ...

    def get_by_user_and_month(
        self,
        user_id: int,
        year: int,
        month: int,
    ) -> list[Expense]:
        """Retrieve all expenses for a given user in a given month.

        Args:
            user_id: The Telegram user id.
            year: The year (e.g., 2026).
            month: The month number (1-12).

        Returns:
            A list of expenses, newest first.
        """
        ...

    def get_months_with_expenses(self, user_id: int, year: int) -> set[int]:
        """Return the set of month numbers (1-12) that have expenses for a user in a year.

        Args:
            user_id: The Telegram user id.
            year: The year (e.g., 2026).

        Returns:
            A set of month numbers with at least one expense (empty set if none).
        """
        ...

    def get_total_by_user_and_year(self, user_id: int, year: int) -> Decimal:
        """Return the sum of all expense amounts for a user in a year.

        Args:
            user_id: The Telegram user id.
            year: The year (e.g., 2026).

        Returns:
            The total amount as Decimal (0.00 if no expenses).
        """
        ...
