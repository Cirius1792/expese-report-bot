# Interactive /list Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/list` Telegram command that shows an interactive expense browser with inline keyboard buttons for month/year navigation.

**Architecture:** Two new methods on `ExpenseRepositoryPort` (months-with-expenses query + year-total query), implemented in `SqliteExpenseRepository`. Two new handler factories in `telegram_bot.py` (command + callback), wired in `main.py`. No new domain types.

**Tech Stack:** Python 3.12+, python-telegram-bot>=21.11, sqlite3, ruff, ty, pytest, behave

## Global Constraints

- Python 3.12+ (use `X | Y` unions, PEP 695 generics)
- Formatter: `ruff format`, Linter: `ruff check`, Type checker: `ty check`
- Test runner: `pytest` for unit tests, `behave` for BDD
- TDD: red-green-refactor, never write implementation before a failing test
- Hexagonal architecture: domain/ has zero framework/IO imports
- Strong typing on all function signatures and class attributes
- After every change: `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest`

---

### Task 1: Extend ExpenseRepositoryPort with two new protocol methods

**Files:**
- Modify: `src/expense_report/ports/repository.py`

**Interfaces:**
- Produces: `get_months_with_expenses(user_id: int, year: int) -> set[int]`, `get_total_by_user_and_year(user_id: int, year: int) -> Decimal`

- [ ] **Step 1: Add the two abstract method signatures to the Protocol**

Add to `src/expense_report/ports/repository.py` after line 33 (`get_by_user_and_month` block ends):

```python
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
```

- [ ] **Step 2: Verify the file is valid**

Run: `uvx ruff check src/expense_report/ports/repository.py`
Expected: PASS (no errors)

- [ ] **Step 3: Commit**

```bash
git add src/expense_report/ports/repository.py
git commit -m "feat: add get_months_with_expenses and get_total_by_user_and_year to port"
```

---

### Task 2: Implement new queries in SqliteExpenseRepository

**Files:**
- Create: `tests/adapters/out/test_sqlite_repository.py` (append new test class)
- Modify: `src/expense_report/adapters/out/sqlite_repository.py`

**Interfaces:**
- Consumes: `get_months_with_expenses(user_id: int, year: int) -> set[int]`, `get_total_by_user_and_year(user_id: int, year: int) -> Decimal` from Task 1
- Produces: Working SQL implementations

- [ ] **Step 1: Write failing tests for the two new methods**

Append to `tests/adapters/out/test_sqlite_repository.py`:

```python
from datetime import date, datetime
from decimal import Decimal

from expense_report.domain.models import Expense


class TestGetMonthsWithExpenses:
    """Tests for get_months_with_expenses query."""

    def test_returns_months_with_expenses(self) -> None:
        """Queries across a year and returns only months that have expenses."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        user_id = 12345

        # Seed: July (2 expenses), March (1 expense), no other months
        for expense_date, merchant in [
            ("2026-07-10", "Shop A"),
            ("2026-07-20", "Shop B"),
            ("2026-03-05", "Shop C"),
        ]:
            repo.save(Expense(
                id=None,
                amount=Decimal("10.00"),
                currency="EUR",
                merchant=merchant,
                date=date.fromisoformat(expense_date),
                category=None,
                user_id=user_id,
                receipt_photo_id=None,
                created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
            ))

        result = repo.get_months_with_expenses(user_id, 2026)
        assert result == {3, 7}

    def test_returns_empty_set_when_no_expenses(self) -> None:
        """Returns empty set for a user with no expenses in that year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        result = repo.get_months_with_expenses(99999, 2026)
        assert result == set()

    def test_multi_user_isolation(self) -> None:
        """Each user sees only their own months."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(Expense(
            id=None, amount=Decimal("10.00"), currency="EUR", merchant="A",
            date=date(2026, 7, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2026, 7, 1, 12, 0, 0),
        ))
        repo.save(Expense(
            id=None, amount=Decimal("20.00"), currency="EUR", merchant="B",
            date=date(2026, 3, 1), category=None, user_id=456,
            receipt_photo_id=None, created_at=datetime(2026, 3, 1, 12, 0, 0),
        ))

        assert repo.get_months_with_expenses(123, 2026) == {7}
        assert repo.get_months_with_expenses(456, 2026) == {3}

    def test_different_years_returned_separately(self) -> None:
        """Querying 2025 returns months only from 2025, not 2026."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(Expense(
            id=None, amount=Decimal("10.00"), currency="EUR", merchant="A",
            date=date(2026, 7, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2026, 7, 1, 12, 0, 0),
        ))
        repo.save(Expense(
            id=None, amount=Decimal("20.00"), currency="EUR", merchant="B",
            date=date(2025, 12, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2025, 12, 1, 12, 0, 0),
        ))

        assert repo.get_months_with_expenses(123, 2025) == {12}
        assert repo.get_months_with_expenses(123, 2026) == {7}


class TestGetTotalByUserAndYear:
    """Tests for get_total_by_user_and_year query."""

    def test_sums_all_expenses_in_year(self) -> None:
        """Returns the sum of all expense amounts for a user in a year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        user_id = 12345

        for expense_date, amount in [
            ("2026-07-10", "42.50"),
            ("2026-07-20", "12.50"),
            ("2026-03-05", "30.00"),
        ]:
            repo.save(Expense(
                id=None,
                amount=Decimal(amount),
                currency="EUR",
                merchant="Shop",
                date=date.fromisoformat(expense_date),
                category=None,
                user_id=user_id,
                receipt_photo_id=None,
                created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
            ))

        result = repo.get_total_by_user_and_year(user_id, 2026)
        assert result == Decimal("85.00")

    def test_returns_zero_when_no_expenses(self) -> None:
        """Returns Decimal 0.00 when no expenses exist for the user/year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")
        result = repo.get_total_by_user_and_year(99999, 2026)
        assert result == Decimal("0.00")

    def test_multi_user_isolation(self) -> None:
        """Each user's total is independent."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(Expense(
            id=None, amount=Decimal("50.00"), currency="EUR", merchant="A",
            date=date(2026, 7, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2026, 7, 1, 12, 0, 0),
        ))
        repo.save(Expense(
            id=None, amount=Decimal("30.00"), currency="EUR", merchant="B",
            date=date(2026, 7, 2), category=None, user_id=456,
            receipt_photo_id=None, created_at=datetime(2026, 7, 2, 12, 0, 0),
        ))

        assert repo.get_total_by_user_and_year(123, 2026) == Decimal("50.00")
        assert repo.get_total_by_user_and_year(456, 2026) == Decimal("30.00")

    def test_only_sums_requested_year(self) -> None:
        """Only sums expenses from the specified year."""
        from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

        repo = SqliteExpenseRepository(":memory:")

        repo.save(Expense(
            id=None, amount=Decimal("100.00"), currency="EUR", merchant="A",
            date=date(2026, 7, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2026, 7, 1, 12, 0, 0),
        ))
        repo.save(Expense(
            id=None, amount=Decimal("50.00"), currency="EUR", merchant="B",
            date=date(2025, 12, 1), category=None, user_id=123,
            receipt_photo_id=None, created_at=datetime(2025, 12, 1, 12, 0, 0),
        ))

        assert repo.get_total_by_user_and_year(123, 2026) == Decimal("100.00")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/out/test_sqlite_repository.py::TestGetMonthsWithExpenses tests/adapters/out/test_sqlite_repository.py::TestGetTotalByUserAndYear -v`
Expected: FAIL — AttributeError on `get_months_with_expenses` / `get_total_by_user_and_year` (not yet implemented)

- [ ] **Step 3: Implement get_months_with_expenses**

Add to `SqliteExpenseRepository` class in `src/expense_report/adapters/out/sqlite_repository.py`, after the `get_by_user_and_month` method:

```python
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
```

- [ ] **Step 4: Implement get_total_by_user_and_year**

Add to `SqliteExpenseRepository` class, after `get_months_with_expenses`:

```python
    def get_total_by_user_and_year(self, user_id: int, year: int) -> Decimal:
        """Return the sum of all expense amounts for a user in a year."""
        prefix = f"{year:04d}-"
        row = self._conn.execute(
            "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0.0) AS total FROM expenses"
            " WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{prefix}%"),
        ).fetchone()

        total = Decimal(str(row["total"]))
        logger.info(
            "Total for user %s in %04d: %s",
            user_id,
            year,
            total,
        )
        return total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/adapters/out/test_sqlite_repository.py::TestGetMonthsWithExpenses tests/adapters/out/test_sqlite_repository.py::TestGetTotalByUserAndYear -v`
Expected: ALL PASS (7 tests)

- [ ] **Step 6: Format, lint, typecheck**

Run: `uvx ruff format && uvx ruff check && uvx ty check`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add tests/adapters/out/test_sqlite_repository.py src/expense_report/adapters/out/sqlite_repository.py
git commit -m "feat: implement get_months_with_expenses and get_total_by_user_and_year in SQLite"
```

---

### Task 3: Add formatting helpers and inline keyboard builder

**Files:**
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py`

**Interfaces:**
- Produces: `_format_month_view(expenses, year, month) -> str`, `_format_year_view(total, year) -> str`, `_build_list_keyboard(active_year, active_month, year_months) -> InlineKeyboardMarkup`

These are pure helper functions with no external dependencies, tested indirectly through handler tests in Tasks 4-5.

- [ ] **Step 1: Add imports for InlineKeyboard classes**

In `src/expense_report/adapters/inbound/telegram_bot.py`, change the imports:

Replace:
```python
from telegram import Update
```

With:
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
```

- [ ] **Step 2: Add month name constant and formatting helpers**

Add after the WELCOME_MESSAGE constant (after line 24):

```python
_MONTH_NAMES: dict[int, str] = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "May", 6: "Jun", 7: "Jul", 8: "Aug",
    9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def _format_month_view(expenses: list[Expense], year: int, month: int) -> str:
    """Format a list of expenses as a month-view message text."""
    month_name = datetime(year, month, 1).strftime("%B")

    if not expenses:
        return f"📊 {month_name} {year}\n\nNo expenses recorded for this month."

    lines = [f"📊 {month_name} {year}\n"]
    total = Decimal("0.00")

    for e in expenses:
        lines.append(
            f"{e.date}  {e.merchant:<20} {e.amount:>8.2f} {e.currency:<4} {e.category or ''}"
        )
        total += e.amount

    lines.append(f"\nTotal: {total:.2f} ({len(expenses)} expenses)")
    lines.append("\nOnly months with recorded expenses are shown below.")

    return "\n".join(lines)


def _format_year_view(total: Decimal, year: int) -> str:
    """Format a year aggregate as a message text."""
    return (
        f"📊 {year} Summary\n\n"
        f"Total: {total:.2f} EUR\n\n"
        f"Tap a month below for details."
    )
```

- [ ] **Step 3: Add keyboard builder helper**

Add after the new formatting helpers:

```python
def _build_list_keyboard(
    active_year: int,
    active_month: int | None,
    year_months: dict[int, set[int]],
) -> InlineKeyboardMarkup:
    """Build an inline keyboard with year and month buttons.

    Args:
        active_year: The currently selected year.
        active_month: The currently selected month, or None for year-view.
        year_months: Mapping of year -> set of month numbers with expenses.

    Returns:
        An InlineKeyboardMarkup with year row and month row.
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    # Year row — descending order
    years = sorted(year_months.keys(), reverse=True)
    if years:
        year_buttons = [
            InlineKeyboardButton(str(y), callback_data=f"year:{y}")
            for y in years
        ]
        keyboard.append(year_buttons)

    # Month row — chronological order, only months with expenses
    months = sorted(year_months.get(active_year, set()))
    if months:
        month_buttons = [
            InlineKeyboardButton(
                _MONTH_NAMES[m],
                callback_data=f"month:{active_year}:{m}",
            )
            for m in months
        ]
        keyboard.append(month_buttons)

    return InlineKeyboardMarkup(keyboard)
```

- [ ] **Step 4: Update test conftest.py to support InlineKeyboardMarkup inspection**

Append to `tests/conftest.py`, right before `sys.modules["telegram"] = mock_telegram`:

```python
# InlineKeyboardButton — simple dataclass for test assertions
class _FakeInlineKeyboardButton:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


# InlineKeyboardMarkup — stores the keyboard for test inspection
class _FakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard: list):
        self.inline_keyboard = inline_keyboard


mock_telegram.InlineKeyboardButton = _FakeInlineKeyboardButton
mock_telegram.InlineKeyboardMarkup = _FakeInlineKeyboardMarkup
```

- [ ] **Step 5: Update Behave environment.py to support InlineKeyboardMarkup inspection**

In `features/environment.py`, add the same fake classes. Find the line `mock_telegram.helpers = mock_helpers` and add after it:

```python
# InlineKeyboardButton — simple dataclass for test assertions
class _BDDFakeInlineKeyboardButton:
    def __init__(self, text: str, callback_data: str):
        self.text = text
        self.callback_data = callback_data


# InlineKeyboardMarkup — stores the keyboard for test inspection
class _BDDFakeInlineKeyboardMarkup:
    def __init__(self, inline_keyboard: list):
        self.inline_keyboard = inline_keyboard


mock_telegram.InlineKeyboardButton = _BDDFakeInlineKeyboardButton
mock_telegram.InlineKeyboardMarkup = _BDDFakeInlineKeyboardMarkup
```

- [ ] **Step 6: Verify the files are valid**

Run: `uvx ruff check src/expense_report/adapters/inbound/telegram_bot.py tests/conftest.py features/environment.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/expense_report/adapters/inbound/telegram_bot.py tests/conftest.py features/environment.py
git commit -m "feat: add list view formatting helpers, inline keyboard builder, and test mock support"
```

---

### Task 4: Build the /list command handler with tests

**Files:**
- Modify: `tests/adapters/inbound/test_telegram_bot.py` (append new test class)
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py`

**Interfaces:**
- Consumes: `_format_month_view`, `_build_list_keyboard` from Task 3; `get_months_with_expenses`, `get_by_user_and_month` from Tasks 1-2
- Produces: `_make_list_handler(repository) -> Callable`

- [ ] **Step 1: Write failing tests for the list command handler**

Append to `tests/adapters/inbound/test_telegram_bot.py`:

```python
from unittest.mock import ANY, AsyncMock, MagicMock, call, patch

from expense_report.domain.models import Expense, ExtractionResult


class TestListHandler:
    """Tests for /list command handler with inline keyboard."""

    def test_shows_current_month_expenses_and_total(self) -> None:
        """List handler shows current month expenses and total."""
        repo = MagicMock()
        repo.get_months_with_expenses.return_value = {7, 3}
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1", amount=Decimal("42.50"), currency="EUR", merchant="Supermarket",
                date=date(2026, 7, 10), category="food", user_id=12345,
                receipt_photo_id=None, created_at=datetime(2026, 7, 10, 10, 0, 0),
            ),
            Expense(
                id="e2", amount=Decimal("12.50"), currency="EUR", merchant="Coffee Shop",
                date=date(2026, 7, 20), category="food", user_id=12345,
                receipt_photo_id=None, created_at=datetime(2026, 7, 20, 11, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_months_with_expenses.assert_any_call(12345, 2026)
        repo.get_months_with_expenses.assert_any_call(12345, 2025)
        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 7)

        # Verify reply includes expense data and total
        reply_text = update.effective_message.reply_text.call_args[1]["text"]
        assert "Supermarket" in reply_text
        assert "Coffee Shop" in reply_text
        assert "55.00" in reply_text
        assert "July 2026" in reply_text

        # Verify reply_markup is an InlineKeyboardMarkup (ANY as placeholder since we mock)
        assert "reply_markup" in update.effective_message.reply_text.call_args[1]

    def test_shows_current_month_and_year_buttons(self) -> None:
        """List handler generates correct inline button labels."""
        from telegram import InlineKeyboardMarkup

        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7, 3},  # 2026
            set(),    # 2025 (none)
        ]
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1", amount=Decimal("42.50"), currency="EUR", merchant="Shop",
                date=date(2026, 7, 10), category=None, user_id=12345,
                receipt_photo_id=None, created_at=datetime(2026, 7, 10, 10, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
        keyboard = markup.inline_keyboard

        # Year row: only 2026 (2025 has no expenses)
        year_buttons = [btn.text for btn in keyboard[0]]
        assert year_buttons == ["2026"]
        assert keyboard[0][0].callback_data == "year:2026"

        # Month row: Jul and Mar
        month_buttons = [btn.text for btn in keyboard[1]]
        assert month_buttons == ["Mar", "Jul"]
        assert keyboard[1][0].callback_data == "month:2026:3"
        assert keyboard[1][1].callback_data == "month:2026:7"

    def test_previous_year_button_when_expenses_exist(self) -> None:
        """Both 2026 and 2025 buttons shown when both years have expenses."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7},     # 2026
            {12, 1}, # 2025
        ]
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1", amount=Decimal("10.00"), currency="EUR", merchant="Shop",
                date=date(2026, 7, 1), category=None, user_id=12345,
                receipt_photo_id=None, created_at=datetime(2026, 7, 1, 10, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
        keyboard = markup.inline_keyboard

        year_buttons = [btn.text for btn in keyboard[0]]
        assert year_buttons == ["2026", "2025"]

    def test_no_expenses_shows_informative_message(self) -> None:
        """When no expenses exist at all, show message without buttons."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            set(),  # 2026
            set(),  # 2025
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        reply_text = update.effective_message.reply_text.call_args[1]["text"]
        assert "no" in reply_text.lower()
        assert "reply_markup" not in update.effective_message.reply_text.call_args[1]

    def test_multi_user_isolation(self) -> None:
        """User 99999 sees a different user_id passed to repo."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7},
            set(),
        ]
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update(user_id=99999)
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_months_with_expenses.assert_any_call(99999, 2026)
        repo.get_by_user_and_month.assert_called_once_with(99999, 2026, 7)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestListHandler -v`
Expected: FAIL — `_make_list_handler` not defined

- [ ] **Step 3: Implement _make_list_handler**

Add to `src/expense_report/adapters/inbound/telegram_bot.py`, after the formatting helpers:

```python
def _make_list_handler(repository: ExpenseRepositoryPort):
    """Factory: create a /list handler bound to the given repository."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping /list update with no effective message or user")
            return

        user_id = update.effective_user.id
        now = datetime.now()
        current_year = now.year
        current_month = now.month

        logger.info("User %s requested /list", user_id)

        # Discover which years and months have expenses
        year_months: dict[int, set[int]] = {}

        current_year_months = repository.get_months_with_expenses(user_id, current_year)
        if current_year_months:
            year_months[current_year] = current_year_months

        prev_year_months = repository.get_months_with_expenses(user_id, current_year - 1)
        if prev_year_months:
            year_months[current_year - 1] = prev_year_months

        if not year_months:
            await update.effective_message.reply_text(
                "You have no recorded expenses."
                " Send me a photo or describe an expense to get started!"
            )
            return

        # Show current month's expenses
        expenses = repository.get_by_user_and_month(user_id, current_year, current_month)

        text = _format_month_view(expenses, current_year, current_month)
        keyboard = _build_list_keyboard(current_year, current_month, year_months)

        await update.effective_message.reply_text(text, reply_markup=keyboard)

    return handler
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestListHandler -v`
Expected: ALL PASS (5 tests)

- [ ] **Step 5: Format, lint, typecheck**

Run: `uvx ruff format && uvx ruff check && uvx ty check`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add tests/adapters/inbound/test_telegram_bot.py src/expense_report/adapters/inbound/telegram_bot.py
git commit -m "feat: add /list command handler with inline keyboard"
```

---

### Task 5: Build the callback query handler with tests

**Files:**
- Modify: `tests/adapters/inbound/test_telegram_bot.py` (append new test class)
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py`

**Interfaces:**
- Consumes: `_format_month_view`, `_format_year_view`, `_build_list_keyboard` from Tasks 3-4; all three repo methods from Tasks 1-2
- Produces: `_make_list_callback_handler(repository) -> Callable`

- [ ] **Step 1: Add a helper for making mock callback updates**

Append to `tests/adapters/inbound/test_telegram_bot.py`:

```python


def _make_callback_update(
    user_id: int = 12345,
    callback_data: str = "",
) -> MagicMock:
    """Create a mock Telegram Update with a CallbackQuery."""
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.from_user = MagicMock()
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    update.effective_message = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


class TestListCallbackHandler:
    """Tests for /list inline keyboard callback handler."""

    def test_month_callback_updates_message(self) -> None:
        """Tapping a month button edits the message to show that month."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1", amount=Decimal("30.00"), currency="EUR", merchant="Book Store",
                date=date(2026, 3, 5), category="shopping", user_id=12345,
                receipt_photo_id=None, created_at=datetime(2026, 3, 5, 10, 0, 0),
            ),
        ]
        repo.get_months_with_expenses.side_effect = [
            {7, 3},  # 2026
            set(),    # 2025
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="month:2026:3")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        # Verify query.answer() was called
        update.callback_query.answer.assert_awaited_once()

        # Verify repository was called for the correct month
        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 3)

        # Verify edit_message_text was called with expense data
        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "Book Store" in edit_call["text"]
        assert "30.00" in edit_call["text"]

        # Verify keyboard was included
        markup = edit_call["reply_markup"]
        keyboard = markup.inline_keyboard
        month_buttons = [btn.text for btn in keyboard[1]]
        assert "Mar" in month_buttons
        assert "Jul" in month_buttons

    def test_year_callback_shows_year_total(self) -> None:
        """Tapping a year button shows year aggregate."""
        repo = MagicMock()
        repo.get_total_by_user_and_year.return_value = Decimal("15.00")
        repo.get_months_with_expenses.side_effect = [
            {7, 3},  # 2026
            {12},    # 2025
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="year:2025")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        update.callback_query.answer.assert_awaited_once()
        repo.get_total_by_user_and_year.assert_called_once_with(12345, 2025)

        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "2025 Summary" in edit_call["text"]
        assert "15.00" in edit_call["text"]

        # Month row shows Dec (2025 months)
        markup = edit_call["reply_markup"]
        keyboard = markup.inline_keyboard
        month_buttons = [btn.text for btn in keyboard[1]]
        assert month_buttons == ["Dec"]

    def test_month_callback_on_empty_month_shows_no_expenses_message(self) -> None:
        """Month with no expense rows shows informative text."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []
        repo.get_months_with_expenses.side_effect = [
            {7},
            set(),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="month:2026:3")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "No expenses" in edit_call["text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestListCallbackHandler -v`
Expected: FAIL — `_make_list_callback_handler` not defined

- [ ] **Step 3: Implement _make_list_callback_handler**

Add to `src/expense_report/adapters/inbound/telegram_bot.py`, after `_make_list_handler`:

```python
def _make_list_callback_handler(repository: ExpenseRepositoryPort):
    """Factory: create a callback handler for /list inline keyboard buttons."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            logger.debug("Skipping callback with no CallbackQuery")
            return

        await query.answer()
        data = query.data
        if data is None:
            return

        user_id = query.from_user.id
        now = datetime.now()

        # Rebuild year_months for keyboard (lightweight queries)
        year_months: dict[int, set[int]] = {}
        current_year_months = repository.get_months_with_expenses(user_id, now.year)
        if current_year_months:
            year_months[now.year] = current_year_months
        prev_year_months = repository.get_months_with_expenses(user_id, now.year - 1)
        if prev_year_months:
            year_months[now.year - 1] = prev_year_months

        if data.startswith("year:"):
            year = int(data.split(":")[1])
            logger.info("User %s selected year %s in /list", user_id, year)

            total = repository.get_total_by_user_and_year(user_id, year)
            text = _format_year_view(total, year)
            keyboard = _build_list_keyboard(year, None, year_months)

            await query.edit_message_text(text=text, reply_markup=keyboard)

        elif data.startswith("month:"):
            _, year_str, month_str = data.split(":")
            year = int(year_str)
            month = int(month_str)
            logger.info("User %s selected month %s/%s in /list", user_id, year, month)

            expenses = repository.get_by_user_and_month(user_id, year, month)
            text = _format_month_view(expenses, year, month)
            keyboard = _build_list_keyboard(year, month, year_months)

            await query.edit_message_text(text=text, reply_markup=keyboard)

    return handler
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestListCallbackHandler -v`
Expected: ALL PASS (3 tests)

- [ ] **Step 5: Format, lint, typecheck**

Run: `uvx ruff format && uvx ruff check && uvx ty check`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add tests/adapters/inbound/test_telegram_bot.py src/expense_report/adapters/inbound/telegram_bot.py
git commit -m "feat: add /list callback query handler for month/year navigation"
```

---

### Task 6: Register handlers and update welcome message

**Files:**
- Modify: `src/expense_report/adapters/inbound/main.py`
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py` (register_handlers, WELCOME_MESSAGE)

**Interfaces:**
- Consumes: `_make_list_handler`, `_make_list_callback_handler` from Tasks 4-5
- Produces: Wired application with `/list` command and callback handler

- [ ] **Step 1: Update register_handlers to add the new handlers**

In `src/expense_report/adapters/inbound/telegram_bot.py`, update the `register_handlers` function:

Replace the existing `register_handlers` body (keep the import of `CallbackQueryHandler` in the file's imports):

First, add `CallbackQueryHandler` to the telegram.ext imports at the top of the file.

Replace:
```python
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
```

With:
```python
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
```

Then update `register_handlers` body:

Replace the existing function body:
```python
def register_handlers(
    app: Application,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
) -> None:
    """Register all bot command and message handlers."""
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("report", _make_report_handler(repository)))
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            _make_photo_handler(extraction_adapter, repository, correction_store),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _make_text_handler(extraction_adapter, repository, correction_store),
        )
    )
```

With:
```python
def register_handlers(
    app: Application,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
) -> None:
    """Register all bot command and message handlers."""
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("report", _make_report_handler(repository)))
    app.add_handler(CommandHandler("list", _make_list_handler(repository)))
    app.add_handler(
        CallbackQueryHandler(
            _make_list_callback_handler(repository),
            pattern=r"^(year|month):",
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            _make_photo_handler(extraction_adapter, repository, correction_store),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _make_text_handler(extraction_adapter, repository, correction_store),
        )
    )
```

- [ ] **Step 2: Update WELCOME_MESSAGE to include /list**

In `src/expense_report/adapters/inbound/telegram_bot.py`, replace:

```python
WELCOME_MESSAGE = """Welcome! I'm your expense report bot.

Send me a photo of a receipt, or describe your expense like "lunch 15 eur".

Commands:
/start - Show this message
/report - Get your monthly expense report as CSV"""
```

With:

```python
WELCOME_MESSAGE = """Welcome! I'm your expense report bot.

Send me a photo of a receipt, or describe your expense like "lunch 15 eur".

Commands:
/start - Show this message
/report - Get your monthly expense report as CSV
/list - Browse your expenses by month"""
```

- [ ] **Step 3: Update handler registration count test**

In `tests/adapters/inbound/test_telegram_bot.py`, in the `TestRegisterHandlers` class, rename the test and update:

Replace the method name `test_registers_all_four_handlers` with `test_registers_all_handlers`, and update the assertion:

```python
    def test_registers_all_handlers(self) -> None:
        """register_handlers adds 6 handlers to the Application."""
        ...
        # Verify 6 handlers were registered
        assert app.add_handler.call_count == 6
        # Expected: CommandHandler(start), CommandHandler(report), CommandHandler(list),
        #           CallbackQueryHandler, MessageHandler(photo), MessageHandler(text)
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -v`
Expected: ALL TESTS PASS

- [ ] **Step 5: Format, lint, typecheck**

Run: `uvx ruff format && uvx ruff check && uvx ty check`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/expense_report/adapters/inbound/telegram_bot.py src/expense_report/adapters/inbound/main.py tests/adapters/inbound/test_telegram_bot.py
git commit -m "feat: register /list command and callback handler, update welcome message"
```

---

### Task 7: BDD feature file and step definitions

**Files:**
- Create: `features/list.feature`
- Create: `features/steps/list_steps.py`

**Interfaces:**
- Consumes: All handlers and helpers from Tasks 1-6
- Produces: BDD acceptance tests running via `behave`

- [ ] **Step 1: Create BDD feature file**

Create `features/list.feature`:

```gherkin
Feature: Monthly Expense List (Interactive)
  As a user
  I want to browse my expenses by month with inline buttons
  So that I can quickly see what I spent in any month

  Background:
    Given the bot is running
    And the database is empty

  @story-11
  Scenario: /list shows current month with total and only months that have expenses
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 12.50  | EUR      | Coffee Shop  | 2026-07-20 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
    When I send the command "/list"
    Then the message shows expenses for July 2026
    And the message shows the total "55.00"
    And the bot shows buttons labeled "Jul" and "Mar"
    And the bot shows a button labeled "2026"
    And the bot does not show a button labeled "2025"
    And the message explains that only months with expenses are shown

  @story-12
  Scenario: /list with no expenses shows informative message without buttons
    Given I have no expenses recorded
    When I send the command "/list"
    Then the bot replies with a message that no expenses are recorded
    And the bot does not show any year or month buttons

  @story-13
  Scenario: /list isolates expenses by user
    Given the following expenses exist:
      | amount | currency | merchant       | date       | user_id |
      | 50.00  | EUR      | User 123 Shop  | 2026-07-01 | 123     |
      | 25.00  | EUR      | User 456 Shop  | 2026-07-02 | 456     |
    When user 123 sends the command "/list"
    Then the message shows expenses for user 123
    And the bot shows a button labeled "Jul"
    And the bot does not show a button labeled "2025"

  @story-14
  Scenario: Tapping a month button navigates to that month
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
    Given the list view for the current month is displayed
    When the user selects month "Mar"
    Then the message updates to show expenses for March 2026
    And the message shows the total "30.00"

  @story-15
  Scenario: Tapping a year button switches to that year and shows year total
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
      | 15.00  | EUR      | Old Shop     | 2025-12-01 | shopping |
    Given the list view for the current month is displayed
    When the user selects year "2025"
    Then the message shows the year total "15.00"
    And the bot shows a button labeled "Dec"
    And the bot does not show a button labeled "Jul"

  @story-16
  Scenario: Previous year button appears only when expenses exist in that year
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 15.00  | EUR      | Old Shop     | 2025-12-01 | shopping |
      | 20.00  | EUR      | Last Jan     | 2025-01-15 | food     |
    When I send the command "/list"
    Then the bot shows a button labeled "2026"
    And the bot shows a button labeled "2025"
    And the bot shows buttons labeled "Jul", "Jan", and "Dec"
```

- [ ] **Step 2: Run behave to verify scenarios are detected (but fail with missing steps)**

Run: `uv run behave features/list.feature --dry-run`
Expected: Lists all 6 scenarios, each step shows "not implemented"

- [ ] **Step 3: Create step definitions**

Create `features/steps/list_steps.py`:

```python
"""Step definitions for interactive /list feature (Stories 11-16)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from behave import given, then, when


# ── Given steps ────────────────────────────────────────────────────────────


@given("the following expenses exist:")
def step_seed_expenses_from_table(context: Any) -> None:
    """Seed multiple expenses from a Gherkin data table.

    Supports optional user_id column for multi-user scenarios.
    """
    from datetime import date, datetime
    from decimal import Decimal

    from expense_report.domain.models import Expense

    for row in context.table:
        user_id = int(row.get("user_id", context.user_id))
        expense = Expense(
            id=None,
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            merchant=row["merchant"],
            date=date.fromisoformat(row["date"]),
            category=row.get("category"),
            user_id=user_id,
            receipt_photo_id=None,
            created_at=datetime.fromisoformat(f"{row['date']}T12:00:00"),
        )
        context.repository.save(expense)


@given("the list view for the current month is displayed")
def step_list_view_displayed(context: Any) -> None:
    """Run the /list handler to set up the initial list view state.

    Captures the InlineKeyboardMarkup on context._list_markup for button-tap tests.
    """
    from expense_report.adapters.inbound.telegram_bot import _make_list_handler

    handler = _make_list_handler(context.repository)
    update = _make_callback_ready_update(context)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.effective_message.reply_text.call_args[1].get("text", "")
    context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")


# ── When steps ─────────────────────────────────────────────────────────────


@when('I send the command "{command}"')
def step_send_command(context: Any, command: str) -> None:
    """Generic command dispatch: sends the command through the appropriate handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_handler

    handler = _make_list_handler(context.repository)
    update = _make_callback_ready_update(context)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.effective_message.reply_text.call_args[1].get("text", "")
    context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")


@when('user {user_id:d} sends the command "{command}"')
def step_user_sends_command(context: Any, user_id: int, command: str) -> None:
    """Send a command from a specific user."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_handler

    handler = _make_list_handler(context.repository)
    update = _make_callback_ready_update(context, user_id=user_id)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.effective_message.reply_text.call_args[1].get("text", "")
    context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")


@when('the user selects month "{month_name}"')
def step_user_selects_month(context: Any, month_name: str) -> None:
    """Find the callback_data for the given month button and invoke the callback handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

    # Find callback_data from the stored markup
    callback_data = _find_button_callback(context._list_markup, month_name)
    assert callback_data is not None, f"Button '{month_name}' not found in keyboard"

    handler = _make_list_callback_handler(context.repository)
    update = _make_callback_query_update(context, callback_data)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.callback_query.edit_message_text.call_args[1]["text"]
    context._list_markup = update.callback_query.edit_message_text.call_args[1]["reply_markup"]


@when('the user selects year "{year}"')
def step_user_selects_year(context: Any, year: str) -> None:
    """Find the callback_data for the given year button and invoke the callback handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

    callback_data = _find_button_callback(context._list_markup, year)
    assert callback_data is not None, f"Button '{year}' not found in keyboard"

    handler = _make_list_callback_handler(context.repository)
    update = _make_callback_query_update(context, callback_data)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.callback_query.edit_message_text.call_args[1]["text"]
    context._list_markup = update.callback_query.edit_message_text.call_args[1]["reply_markup"]


# ── Then steps ─────────────────────────────────────────────────────────────


@then('the message shows expenses for {month_name} {year:d}')
def step_message_shows_month(context: Any, month_name: str, year: int) -> None:
    text = context._list_message_text
    assert month_name in text, f"Expected '{month_name}' in message, got: {text[:200]}"
    assert str(year) in text, f"Expected '{year}' in message, got: {text[:200]}"


@then('the message shows the total "{total}"')
def step_message_shows_total(context: Any, total: str) -> None:
    text = context._list_message_text
    assert total in text, f"Expected total '{total}' in message, got: {text[:200]}"


@then('the message shows the year total "{total}"')
def step_message_shows_year_total(context: Any, total: str) -> None:
    text = context._list_message_text
    assert total in text, f"Expected year total '{total}' in message, got: {text[:200]}"
    assert "Summary" in text, f"Expected 'Summary' in year view, got: {text[:200]}"


@then('the bot shows buttons labeled "{label1}" and "{label2}"')
def step_buttons_labeled_two(context: Any, label1: str, label2: str) -> None:
    labels = _get_all_button_labels(context._list_markup)
    assert label1 in labels, f"Expected button '{label1}', got buttons: {labels}"
    assert label2 in labels, f"Expected button '{label2}', got buttons: {labels}"


@then('the bot shows a button labeled "{label}"')
def step_button_labeled(context: Any, label: str) -> None:
    labels = _get_all_button_labels(context._list_markup)
    assert label in labels, f"Expected button '{label}', got buttons: {labels}"


@then('the bot does not show a button labeled "{label}"')
def step_no_button_labeled(context: Any, label: str) -> None:
    labels = _get_all_button_labels(context._list_markup)
    assert label not in labels, f"Button '{label}' should not be present, got buttons: {labels}"


@then("the message explains that only months with expenses are shown")
def step_explanation_message(context: Any) -> None:
    text = context._list_message_text
    assert "only months" in text.lower(), (
        f"Expected explanation about months, got: {text[:200]}"
    )


@then("the bot replies with a message that no expenses are recorded")
def step_no_expenses_message(context: Any) -> None:
    text = context._list_message_text
    assert "no" in text.lower() and "expense" in text.lower(), (
        f"Expected no-expenses message, got: {text[:200]}"
    )


@then("the bot does not show any year or month buttons")
def step_no_buttons(context: Any) -> None:
    assert context._list_markup is None or context._list_markup == [], (
        f"Expected no buttons, got: {context._list_markup}"
    )


@then('the message shows expenses for user {user_id:d}')
def step_message_user_expenses(context: Any, user_id: int) -> None:
    text = context._list_message_text
    # Verify the reply contains expense data (merchant should match user-specific data)
    assert f"User {user_id}" in text or "Shop" in text, (
        f"Expected user {user_id} expenses, got: {text[:200]}"
    )


@then('the message updates to show expenses for {month_name} {year:d}')
def step_message_updates_month(context: Any, month_name: str, year: int) -> None:
    text = context._list_message_text
    assert month_name in text, f"Expected '{month_name}' in updated message, got: {text[:200]}"
    assert str(year) in text, f"Expected '{year}' in updated message, got: {text[:200]}"


@then('the bot shows buttons labeled "{l1}", "{l2}", and "{l3}"')
def step_buttons_labeled_three(context: Any, l1: str, l2: str, l3: str) -> None:
    labels = _get_all_button_labels(context._list_markup)
    assert l1 in labels, f"Expected '{l1}', got: {labels}"
    assert l2 in labels, f"Expected '{l2}', got: {labels}"
    assert l3 in labels, f"Expected '{l3}', got: {labels}"


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_callback_ready_update(
    context: Any, user_id: int | None = None
) -> MagicMock:
    """Create a mock Update that captures reply_text calls."""
    uid = user_id if user_id is not None else context.user_id
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.reply_document = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = uid
    return update


def _make_callback_ready_context(context: Any) -> MagicMock:
    """Create a mock CallbackContext."""
    return MagicMock()


def _make_callback_query_update(context: Any, callback_data: str) -> MagicMock:
    """Create a mock Update with a CallbackQuery for button-tap tests."""
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.from_user = MagicMock()
    query.from_user.id = context.user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    return update


def _get_all_button_labels(markup: Any) -> list[str]:
    """Extract all button text labels from an InlineKeyboardMarkup mock."""
    if markup is None:
        return []
    labels: list[str] = []
    keyboard = markup.inline_keyboard
    for row in keyboard:
        for btn in row:
            labels.append(btn.text)
    return labels


def _find_button_callback(markup: Any, label: str) -> str | None:
    """Find the callback_data for a button with the given label."""
    if markup is None:
        return None
    keyboard = markup.inline_keyboard
    for row in keyboard:
        for btn in row:
            if btn.text == label:
                return btn.callback_data
    return None
```

- [ ] **Step 4: Run BDD tests**

Run: `uv run behave features/list.feature -v`
Expected: 6 scenarios pass

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest && uv run behave`
Expected: All pytest tests + all behave scenarios pass

- [ ] **Step 6: Format, lint, typecheck**

Run: `uvx ruff format && uvx ruff check && uvx ty check`
Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add features/list.feature features/steps/list_steps.py
git commit -m "feat: add BDD acceptance tests for /list command"
```

---

### Task 8: Final verification — full suite

- [ ] **Step 1: Run full quality pipeline**

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest -v && uv run behave
```

Expected: Everything passes — formatting clean, no lint errors, no type errors, all pytest tests pass, all behave scenarios pass.

- [ ] **Step 2: Verify the plan is complete — all tasks done**

```bash
git log --oneline -8
```

Expected: 8 commits covering all tasks.
