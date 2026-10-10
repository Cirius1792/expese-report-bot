"""Read the migrated database through the PR image's real repository."""

from __future__ import annotations

import json

from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository


def main() -> int:
    repository = SqliteExpenseRepository("/data/expenses.db")
    expenses = repository.get_by_user_and_month(42, 2026, 1)
    print(
        json.dumps(
            [
                {
                    "id": expense.id,
                    "amount": str(expense.amount),
                    "currency": expense.currency,
                    "merchant": expense.merchant,
                    "date": expense.date.isoformat(),
                    "category": expense.category,
                    "deleted_at": (
                        expense.deleted_at.isoformat() if expense.deleted_at is not None else None
                    ),
                }
                for expense in expenses
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
