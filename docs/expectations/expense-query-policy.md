# Expense Query Policy — Browsing, Reporting, and Deletion

## Scope
ARCH-003: Move `/list` (period discovery + browsing), `/report` (CSV export), and
`/delete` (expense removal) flows from the Telegram adapter into an application-owned
`ExpenseQueryPort` + `ExpenseQueryUseCase`, leaving only Telegram-specific rendering
(keyboards, text formatting, BytesIO delivery, callback parsing) in the adapter.

## Architecture Boundary
```
telegram_bot.py          →  ExpenseQueryPort (Protocol in ports/)
  (rendering only)            ↑
                              │ implements
                    application/expense_queries.py
                    ExpenseQueryUseCase(repository)
                              │
                              ↓
                    ExpenseRepositoryPort (driven, unchanged)
```

## Port Shape

```python
class ExpenseQueryPort(Protocol):
    def discover_periods(
        self, user_id: int, *, extra_years: set[int] | None = None
    ) -> PeriodSummary: ...

    def get_month_expenses(self, user_id: int, year: int, month: int) -> list[Expense]: ...

    def get_year_expenses(self, user_id: int, year: int) -> list[Expense]: ...

    def generate_csv_report(self, user_id: int, year: int, month: int) -> str: ...

    def delete_expense(self, user_id: int, expense_id: int) -> DeletionResult: ...
```

## Output DTOs

- `PeriodSummary`: `periods: dict[int, set[int]]`, `active_year: int`, `active_month: int`
- `DeletionResult`: `deleted: Expense | None`

## Behaviors

### 1. Period Discovery (`discover_periods`)
- **Default years**: scans current year + previous year
- **extra_years**: when provided, additionally scans those years (used by callback
  navigation when user selects a year outside the default range)
- **Merging**: collects `set[int]` of months for each year that has expenses
- **Active period selection**:
  - If current month has data → active = current year/month
  - Otherwise → active = most recent year/month with data
  - If no data at all → active = current year/month, periods = {} (empty)

### 2. Month Expenses (`get_month_expenses`)
- Returns `list[Expense]` for the given user/year/month
- Returns empty list if no expenses

### 3. Year Expenses (`get_year_expenses`)
- Aggregates expenses across all months of the given year
- Returns empty list if no expenses
- Sort order: by month then by expense ID (consistent with current behavior)

### 4. CSV Report (`generate_csv_report`)
- Fetches current-month (or caller-specified month) expenses
- Calls `generate_csv(expenses)` from domain
- Returns the CSV string
- Returns header-only CSV for empty expense list (current behavior)

### 5. Deletion (`delete_expense`)
- Calls `repository.delete_by_id(user_id, expense_id)`
- Returns `DeletionResult(deleted=expense)` on success
- Returns `DeletionResult(deleted=None)` if expense not found

## What Stays in the Adapter
- `_format_month_view(expenses, year, month) -> str` — view rendering
- `_format_year_view(expenses, year) -> str` — view rendering
- `_build_list_keyboard(active_year, year_months) -> InlineKeyboardMarkup` — Telegram keyboard
- `_html_escape(text)` — HTML sanitization (already a utility)
- Callback data parsing: `year:YYYY`, `month:YYYY:MM`, `delete:ID`
- Command parsing: `/delete <id>`
- `BytesIO` wrapping + `reply_document` for CSV delivery
- Strikethrough rendering for delete callbacks

## Non-Behaviors (regression guards)
- `/list` with no expenses → "You have no recorded expenses." (unchanged)
- `/list` current month has expenses → shows month view with totals (unchanged)
- `/list` previous year has expenses but current doesn't → shows previous year (unchanged)
- `/list` callback `year:YYYY` → shows year summary view (unchanged)
- `/list` callback `month:YYYY:MM` → shows month detail view (unchanged)
- `/report` with expenses → sends CSV file + confirmation text (unchanged)
- `/report` no expenses → "No expenses recorded for YYYY-MM." (unchanged)
- `/delete <id>` success → confirmation with expense details (unchanged)
- `/delete <id>` not found → "Expense #N was not found." (unchanged)
- `/delete <id>` invalid format → "Usage: /delete <expense_id>" (unchanged)
- Delete callback button → strikethrough + "🗑️ Deleted." (unchanged)
- Delete callback not found → "Expense not found." as callback answer (unchanged)
- Save confirmation still includes delete button (regression from ARCH-001)
- Month view still shows totals by currency with count (regression)

## CSV Placement Decision
`generate_csv()` stays in `domain/csv_generator.py`. It is a pure function (stdlib
`csv` only, zero framework/IO dependencies). This satisfies the domain rule "no
framework/IO imports." If multiple output formats emerge in the future (JSON, XLSX),
a purpose-named Interface can be introduced at that Seam.

## Verification
- `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave`
- Application tests: new `tests/application/test_expense_queries.py` covering all
  five port methods + edge cases
- Adapter tests: update `test_telegram_bot.py` to wire `ExpenseQueryPort` mock
  instead of `ExpenseRepositoryPort` mock in browse/report/delete tests
- Behave: 27 scenarios must remain green (no feature changes)
- Existing extraction/recording tests must remain green (no regression)
