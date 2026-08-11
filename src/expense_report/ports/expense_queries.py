"""Driving port for expense query-side operations — browsing, reporting, and deletion.

All Telegram browse/report/delete flows route through this protocol so the
adapter never touches the driven repository directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from expense_report.domain.models import Expense


@dataclass
class PeriodSummary:
    """Result of period discovery — which years/months have expenses and which is active."""

    periods: dict[int, set[int]] = field(default_factory=dict)
    active_year: int = 0
    active_month: int = 0


@dataclass
class DeletionResult:
    """Result of an expense deletion attempt."""

    deleted: Expense | None = None


class ExpenseQueryPort(Protocol):
    """Driving port for expense query-side operations.

    Each method corresponds to a distinct user-facing operation:
    - discover_periods: which years/months have data (list command + navigation)
    - get_month_expenses: detail view for a single month
    - get_year_expenses: aggregated view for a year
    - generate_csv_report: CSV export for a month
    - delete_expense: remove a single expense
    """

    def discover_periods(
        self, user_id: int, *, extra_years: set[int] | None = None
    ) -> PeriodSummary:
        """Discover which periods have expenses and pick the active period.

        By default scans current year + previous year. Pass extra_years to
        include additional years (used by callback navigation).
        """
        ...

    def get_month_expenses(self, user_id: int, year: int, month: int) -> list[Expense]:
        """Return all expenses for a specific user/year/month."""
        ...

    def get_year_expenses(self, user_id: int, year: int) -> list[Expense]:
        """Return all expenses for a specific user/year, across all months."""
        ...

    def generate_csv_report(self, user_id: int, year: int, month: int) -> str:
        """Generate a CSV report string for the given period."""
        ...

    def delete_expense(self, user_id: int, expense_id: int) -> DeletionResult:
        """Delete a single expense. Returns DeletionResult with the deleted
        Expense or None if not found."""
        ...


__all__ = [
    "DeletionResult",
    "ExpenseQueryPort",
    "PeriodSummary",
]
