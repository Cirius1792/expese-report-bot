"""Expense query use case — browse, report, and delete workflows.

Owns period discovery, expense aggregation, CSV report generation, and deletion
policy. The Telegram adapter calls these methods through ExpenseQueryPort instead
of touching the repository directly.
"""

from __future__ import annotations

from datetime import datetime

from expense_report.domain.csv_generator import generate_csv as _generate_csv
from expense_report.domain.models import Expense
from expense_report.ports.expense_queries import DeletionResult, PeriodSummary
from expense_report.ports.repository import ExpenseRepositoryPort


class ExpenseQueryUseCase:
    """Application use case for expense query-side operations.

    Wraps the driven ExpenseRepositoryPort and exposes browse/report/delete
    operations through the driving ExpenseQueryPort protocol.
    """

    def __init__(self, repository: ExpenseRepositoryPort) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Period discovery
    # ------------------------------------------------------------------

    def discover_periods(
        self, user_id: int, *, extra_years: set[int] | None = None
    ) -> PeriodSummary:
        """Discover which years/months have expenses and pick the active period.

        By default scans current year + previous year. Pass *extra_years* to
        include additional years beyond the default scan range.
        """
        now = datetime.now()
        years_to_scan: set[int] = {now.year, now.year - 1}
        if extra_years:
            years_to_scan |= extra_years

        periods: dict[int, set[int]] = {}
        for year in sorted(years_to_scan, reverse=True):
            months = self._repo.get_months_with_expenses(user_id, year)
            if months:
                periods[year] = months

        # Pick active period
        if now.year in periods and now.month in periods[now.year]:
            active_year = now.year
            active_month = now.month
        elif periods:
            active_year = max(periods.keys())
            active_month = max(periods[active_year])
        else:
            active_year = now.year
            active_month = now.month

        return PeriodSummary(
            periods=periods,
            active_year=active_year,
            active_month=active_month,
        )

    # ------------------------------------------------------------------
    # Expense retrieval
    # ------------------------------------------------------------------

    def get_month_expenses(self, user_id: int, year: int, month: int) -> list[Expense]:
        """Return all expenses for a specific user/year/month."""
        return self._repo.get_by_user_and_month(user_id, year, month)

    def get_year_expenses(self, user_id: int, year: int) -> list[Expense]:
        """Return all expenses for a specific user/year, across all months."""
        months = self._repo.get_months_with_expenses(user_id, year)
        result: list[Expense] = []
        for month in sorted(months):
            result.extend(self._repo.get_by_user_and_month(user_id, year, month))
        return result

    # ------------------------------------------------------------------
    # CSV report
    # ------------------------------------------------------------------

    def generate_csv_report(self, user_id: int, year: int, month: int) -> str:
        """Generate a CSV report string for the given period."""
        expenses = self._repo.get_by_user_and_month(user_id, year, month)
        return _generate_csv(expenses)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    def delete_expense(self, user_id: int, expense_id: int) -> DeletionResult:
        """Delete a single expense and return the result."""
        deleted = self._repo.delete_by_id(user_id, expense_id)
        return DeletionResult(deleted=deleted)
