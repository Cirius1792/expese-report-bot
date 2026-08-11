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
- ✅ All checks pass at HEAD 2ba77a4
- Application tests: new `tests/application/test_expense_queries.py` covering all
  five port methods + edge cases
- Adapter tests: update `test_telegram_bot.py` to wire `ExpenseQueryPort` mock
  instead of `ExpenseRepositoryPort` mock in browse/report/delete tests
- Behave: 27 scenarios must remain green (no feature changes)
- Existing extraction/recording tests must remain green (no regression)


## Evidence

### Final verification chain (HEAD 2ba77a4)

```
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
97 files left unchanged
All checks passed!
All checks passed!
============================= 213 passed in 10.38s ==============================
7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
```

### Expectation-to-Test Mapping

| # | Expectation | Executed Evidence |
|---|---|---|
| 1 | discover_periods: current year has data → active=current | `test_current_year_has_data_uses_current_month_as_active` — PeriodSummary(periods={2026:{7,3}}, active_year=2026, active_month=7) |
| 2 | discover_periods: current empty, previous has → active=previous-most-recent | `test_current_year_no_data_previous_has_uses_most_recent` — PeriodSummary(periods={2025:{12,1}}, active_year=2025, active_month=12) |
| 3 | discover_periods: no data at all → active=current, periods={} | `test_no_expenses_at_all_returns_default_active` — periods={}, active_year=2026, active_month=7 |
| 4 | discover_periods: extra_years → scanned in addition to defaults | `test_extra_years_are_also_scanned` — periods includes 2024 alongside 2026 |
| 5 | discover_periods: multi-user isolation | `test_multi_user_isolation` — repo queried with user_id=99999 |
| 6 | get_month_expenses: returns expenses for period | `test_returns_expenses_for_given_period` — repo.get_by_user_and_month(12345, 2026, 7) |
| 7 | get_month_expenses: empty → [] | `test_returns_empty_list_when_no_expenses` — assert result == [] |
| 8 | get_year_expenses: aggregates across months | `test_aggregates_across_all_months` — 3 expenses from 3 months, repo queried per month |
| 9 | get_year_expenses: empty → [] | `test_returns_empty_list_when_year_has_no_data` — assert result == [] |
| 10 | generate_csv_report: generates CSV with data | `test_generates_csv_for_given_period` — header + data rows present |
| 11 | generate_csv_report: empty → header-only | `test_empty_period_returns_header_only` — 1 line (header only) |
| 12 | delete_expense: success → DeletionResult(deleted=...) | `test_successful_delete_returns_deleted_expense` — result.deleted is the expense |
| 13 | delete_expense: not found → DeletionResult(deleted=None) | `test_not_found_returns_none_deleted` — result == DeletionResult(deleted=None) |
| 14 | /list handler: empty periods → "you have no recorded expenses" | `test_no_expenses_shows_informative_message` — reply contains "no" |
| 15 | /list handler: with data → month view + total + keyboard | `test_shows_current_month_expenses_and_total` — "Supermarket", "55.00", "July 2026", reply_markup present |
| 16 | /list handler: year/month buttons | `test_shows_current_month_and_year_buttons` — year row ["2026"], month row ["Mar","Jul"] |
| 17 | /list handler: both years have data → both buttons | `test_previous_year_button_when_expenses_exist` — year buttons ["2026","2025"] |
| 18 | /list handler: previous year only → shows that year | `test_previous_year_only_shows_that_year` — get_month_expenses(12345, 2025, 12), year buttons ["2025"] |
| 19 | /list handler: multi-user isolation | `test_multi_user_isolation` — discover_periods(99999), get_month_expenses(99999, 2026, 7) |
| 20 | /list callback: month tap → edits message | `test_month_callback_updates_message` — get_month_expenses(12345, 2026, 3), "Book Store" |
| 21 | /list callback: year tap → year summary | `test_year_callback_shows_year_total` — "2025 Summary", "15.00 EUR" |
| 22 | /list callback: empty month → "No expenses" | `test_month_callback_on_empty_month_shows_no_expenses_message` — "No expenses" in text |
| 23 | /list callback: malformed data → no crash | `test_malformed_callback_data_does_not_crash[5 params]` — edit_message_text NOT called |
| 24 | /report: with expenses → CSV document + count | `test_with_expenses_sends_csv` — csv content verified, "Generated report with 2 expenses" |
| 25 | /report: no expenses → "No expenses recorded" | `test_no_expenses_reports_empty` — reply_text "No expenses recorded for 2026-07", no document |
| 26 | /report: multi-user isolation | `test_multi_user_isolation` — generate_csv_report(99999, 2026, 7) |
| 27 | /delete command: success → audit summary | `test_delete_success_replies_with_audit_summary` — "🗑️ Deleted expense #42..." |
| 28 | /delete command: not found → "not found" | `test_delete_not_found_replies_with_not_found_message` — "Expense #99 was not found." |
| 29 | /delete command: invalid format → usage | `test_delete_invalid_format_returns_usage` — 3 invalid inputs all return usage |
| 30 | /delete command: non-positive → usage | `test_delete_non_positive_id_returns_usage` — "/delete 0" → usage |
| 31 | /delete callback: success → strikethrough + deleted | `test_delete_button_edits_message_with_strikethrough` — <s> tag, "🗑️ Deleted.", parse_mode="HTML" |
| 32 | /delete callback: not found → callback answer only | `test_delete_callback_not_found_answers_callback_only` — answer("Expense not found."), edit NOT called |
| 33 | register_handlers: 8 handlers registered, now takes queries | `test_registers_all_handlers` — register_handlers(app, recording, queries), call_count==8 |
| 34 | Format helpers unchanged | `test_format_month_view_includes_expense_ids` — "#42" in text |
| 35 | Save confirmation still has delete button (regression) | `test_save_confirmation_includes_id_and_delete_button` — passes |

### Red-state evidence (commit 093fb60)

32 tests failed before implementation:
- 14 new application tests (ExpenseQueryUseCase not yet implemented)
- 15 adapter tests (handler factories still expected repository, not query port)
- 3 logging tests (ExpenseQueryPort not imported)

### Production code changes

| File | Change |
|------|--------|
| `ports/expense_queries.py` | New Protocol + DTOs (PeriodSummary, DeletionResult, ExpenseQueryPort) |
| `application/expense_queries.py` | New use case: period discovery, aggregation, CSV, deletion |
| `telegram_bot.py` | All handler factories take ExpenseQueryPort; repository import removed; register_handlers(app, recording, queries) |
| `main.py` | Constructs ExpenseQueryUseCase(repository); passes to register_handlers |
| Behave environment + steps | context.expense_queries constructed and passed to handler factories |

### What stayed in the adapter

- `_format_month_view`, `_format_year_view` — text rendering (unchanged)
- `_build_list_keyboard` — Telegram InlineKeyboardMarkup (unchanged)
- `_html_escape` — HTML sanitization (unchanged, already a utility)
- Callback data parsing: `year:YYYY`, `month:YYYY:MM`, `delete:ID` (unchanged)
- Command parsing: `/delete <id>` (unchanged)
- `BytesIO` wrapping + `reply_document` for CSV delivery (unchanged)
- Strikethrough rendering for delete callbacks (unchanged)
