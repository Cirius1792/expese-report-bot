"""Protocol compliance tests for ExpenseRepositoryPort."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from expense_report.domain.models import Expense
from expense_report.ports.repository import ExpenseRepositoryPort


class TestExpenseRepositoryPortProtocol:
    """Verify that a class implementing ExpenseRepositoryPort satisfies the protocol."""

    def test_protocol_compliance(self) -> None:
        """An object with save/get_by_id/get_by_user_and_month methods
        should be recognized as an ExpenseRepositoryPort implementation."""

        class FakeRepository:
            def __init__(self) -> None:
                self._store: dict[str, Expense] = {}

            def save(self, expense: Expense) -> Expense:
                stored = Expense(
                    id="stored-001" if expense.id is None else expense.id,
                    amount=expense.amount,
                    currency=expense.currency,
                    merchant=expense.merchant,
                    date=expense.date,
                    category=expense.category,
                    user_id=expense.user_id,
                    receipt_photo_id=expense.receipt_photo_id,
                    created_at=expense.created_at,
                )
                assert stored.id is not None
                self._store[stored.id] = stored
                return stored

            def get_by_id(self, expense_id: str) -> Expense | None:
                return self._store.get(expense_id)

            def get_by_user_and_month(
                self,
                user_id: int,
                year: int,
                month: int,
            ) -> list[Expense]:
                return [
                    e
                    for e in self._store.values()
                    if e.user_id == user_id and e.date.year == year and e.date.month == month
                ]

            def get_months_with_expenses(self, user_id: int, year: int) -> set[int]:
                return {
                    e.date.month
                    for e in self._store.values()
                    if e.user_id == user_id and e.date.year == year
                }

            def get_total_by_user_and_year(self, user_id: int, year: int) -> Decimal:
                return sum(
                    (e.amount for e in self._store.values() if e.user_id == user_id and e.date.year == year),
                    Decimal("0"),
                )

        repo = FakeRepository()
        assert isinstance(repo, ExpenseRepositoryPort), (
            "FakeRepository must satisfy ExpenseRepositoryPort protocol"
        )

    def test_save_and_retrieve(self) -> None:
        """Save an expense and retrieve it by id."""

        class SimpleRepo:
            def __init__(self) -> None:
                self._store: dict[str, Expense] = {}

            def save(self, expense: Expense) -> Expense:
                stored = Expense(
                    id="exp-42",
                    amount=expense.amount,
                    currency=expense.currency,
                    merchant=expense.merchant,
                    date=expense.date,
                    category=expense.category,
                    user_id=expense.user_id,
                    receipt_photo_id=expense.receipt_photo_id,
                    created_at=expense.created_at,
                )
                self._store["exp-42"] = stored
                return stored

            def get_by_id(self, expense_id: str) -> Expense | None:
                return self._store.get(expense_id)

            def get_by_user_and_month(
                self,
                user_id: int,
                year: int,
                month: int,
            ) -> list[Expense]:
                return [
                    e
                    for e in self._store.values()
                    if e.user_id == user_id and e.date.year == year and e.date.month == month
                ]

        repo = SimpleRepo()
        dt = datetime(2026, 7, 1, 12, 0, 0)
        expense = Expense(
            id=None,
            amount=Decimal("10.00"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category=None,
            user_id=42,
            receipt_photo_id=None,
            created_at=dt,
        )

        saved = repo.save(expense)
        assert saved.id == "exp-42"

        retrieved = repo.get_by_id("exp-42")
        assert retrieved is not None
        assert retrieved.amount == Decimal("10.00")
        assert retrieved.merchant == "Shop"
