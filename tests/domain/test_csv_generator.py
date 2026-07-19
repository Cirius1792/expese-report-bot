"""Tests for csv_generator domain function.

Tests cover CSV generation from Expense records — pure domain logic
with zero framework/IO imports.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from expense_report.domain.csv_generator import generate_csv
from expense_report.domain.models import Expense


class TestGenerateCsv:
    """CSV generation from Expense records."""

    def test_header_line(self) -> None:
        """CSV output starts with the correct header row."""
        expenses: list[Expense] = []
        csv_output = generate_csv(expenses)
        lines = csv_output.strip().split("\n")
        assert lines[0] == "date,merchant,category,amount,currency"

    def test_single_expense(self) -> None:
        """A single expense produces one data row."""
        expense = Expense(
            id="test-1",
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Supermarket",
            date=date(2026, 7, 15),
            category="food",
            user_id=123,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )
        csv_output = generate_csv([expense])
        lines = csv_output.strip().split("\n")
        assert len(lines) == 2  # header + 1 data row
        assert lines[1] == "2026-07-15,Supermarket,food,42.50,EUR"

    def test_category_none_uses_empty_string(self) -> None:
        """When category is None, CSV shows an empty field."""
        expense = Expense(
            id="test-2",
            amount=Decimal("15.00"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 10),
            category=None,
            user_id=456,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 10, 9, 0, 0),
        )
        csv_output = generate_csv([expense])
        lines = csv_output.strip().split("\n")
        fields = lines[1].split(",")
        # category is the 3rd field (0-indexed: date, merchant, category, amount, currency)
        assert fields[2] == ""

    def test_multiple_expenses(self) -> None:
        """Multiple expenses produce one row each."""
        expenses = [
            Expense(
                id="a",
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="Shop A",
                date=date(2026, 7, 1),
                category="shopping",
                user_id=1,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            ),
            Expense(
                id="b",
                amount=Decimal("20.00"),
                currency="EUR",
                merchant="Shop B",
                date=date(2026, 7, 2),
                category="food",
                user_id=1,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 2, 11, 0, 0),
            ),
            Expense(
                id="c",
                amount=Decimal("30.00"),
                currency="USD",
                merchant="Shop C",
                date=date(2026, 7, 3),
                category="transport",
                user_id=1,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 3, 12, 0, 0),
            ),
        ]
        csv_output = generate_csv(expenses)
        lines = csv_output.strip().split("\n")
        assert len(lines) == 4  # header + 3 data rows
        assert lines[1] == "2026-07-01,Shop A,shopping,10.00,EUR"
        assert lines[2] == "2026-07-02,Shop B,food,20.00,EUR"
        assert lines[3] == "2026-07-03,Shop C,transport,30.00,USD"

    def test_decimal_formatting_two_places(self) -> None:
        """Decimal amounts are formatted with exactly 2 decimal places."""
        expense = Expense(
            id="test-3",
            amount=Decimal("99.9"),
            currency="EUR",
            merchant="Store",
            date=date(2026, 7, 20),
            category="goods",
            user_id=1,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 20, 14, 0, 0),
        )
        csv_output = generate_csv([expense])
        lines = csv_output.strip().split("\n")
        fields = lines[1].split(",")
        assert fields[3] == "99.90"  # formatted to 2 decimal places

    def test_empty_list_returns_header_only(self) -> None:
        """An empty expenses list returns just the header line."""
        csv_output = generate_csv([])
        lines = csv_output.strip().split("\n")
        assert len(lines) == 1
        assert lines[0] == "date,merchant,category,amount,currency"
