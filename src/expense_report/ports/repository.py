"""Port interface for expense repository storage."""

from __future__ import annotations

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

    def get_by_id(self, expense_id: str) -> Expense | None:
        """Retrieve a single expense by its unique identifier.

        Args:
            expense_id: The persistent id of the expense.

        Returns:
            The expense if found, None otherwise.
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
