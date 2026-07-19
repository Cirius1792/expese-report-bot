"""Pure domain function for CSV generation from Expense records.

This module MUST have zero framework/IO imports.
"""

from __future__ import annotations

import csv
from io import StringIO

from expense_report.domain.models import Expense


def generate_csv(expenses: list[Expense]) -> str:
    """Generate a CSV string from a list of expenses.

    Headers: date,merchant,category,amount,currency
    Category is included even if None (empty string in CSV).
    Decimal amounts are formatted with 2 decimal places.
    """
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow(["date", "merchant", "category", "amount", "currency"])

    for expense in expenses:
        writer.writerow(
            [
                expense.date.isoformat(),
                expense.merchant,
                expense.category if expense.category is not None else "",
                f"{expense.amount:.2f}",
                expense.currency,
            ]
        )

    return output.getvalue()
