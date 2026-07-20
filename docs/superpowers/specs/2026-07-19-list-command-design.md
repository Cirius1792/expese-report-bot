# Design: Interactive `/list` Command

**Date:** 2026-07-19
**Status:** Draft

## Overview

Add a `/list` command to the Telegram bot that shows an interactive month-by-month expense browser with inline keyboard buttons. The user sees the current month's expenses on first load and can tap buttons to navigate between months and years.

## Interaction Flow

1. **User sends `/list`** → bot replies with current month's expense list + total, plus two rows of inline buttons:
   - Row 1: year buttons (e.g., `[2025] [2026]`) — only years with expenses
   - Row 2: month buttons (e.g., `[Mar] [Jul]`) — only months with expenses for the active year
   - Message includes explanatory note: "Only months where you've recorded expenses are shown below."

2. **User taps a year button** (e.g., `[2025]`) → message edits to show that year's total. Active year changes. Month buttons reload to show that year's months.

3. **User taps a month button** (e.g., `[Mar]`) → message edits to show that month's expense list + total for the active year.

4. **Initial state** on `/list`: active year = current year, active month = current month.

### Visual Examples

**Year view** (tapping `[2026]`):
```
📊 2026 Summary

Total: 1,240.50 EUR

Tap a month below for details.

[2025] [2026]
[Jan] [Mar] [May] [Jun] [Jul]
```

**Month view** (tapping `[Jul]` or initial `/list`):
```
📊 July 2026

2026-07-15  Supermarket     42.50 EUR  food
2026-07-20  Coffee Shop     12.50 EUR  food

Total: 55.00 EUR (2 expenses)

Only months with recorded expenses are shown below.

[2025] [2026]
[Jan] [Mar] [Jul]
```

## Architecture

Follows existing hexagonal (ports & adapters) pattern. No new domain types needed — `Expense` and `ExpenseRepositoryPort` are sufficient.

### New Port Methods

Two new query methods on `ExpenseRepositoryPort`:

| Method | Purpose | SQL |
|--------|---------|-----|
| `get_months_with_expenses(user_id, year) → set[int]` | Which months in a given year have expenses | `SELECT DISTINCT strftime('%m', date) FROM expenses WHERE user_id=? AND date LIKE ?` |
| `get_total_by_user_and_year(user_id, year) → Decimal` | Year aggregate total | `SELECT SUM(CAST(amount AS REAL)) FROM expenses WHERE user_id=? AND date LIKE ?` |

Existing `get_by_user_and_month` handles month detail queries — no change needed.

### Adapter Changes

**`sqlite_repository.py`**: Implement `get_months_with_expenses` and `get_total_by_user_and_year`.

**`telegram_bot.py`**: 
- New `_make_list_handler(repository)` factory — handles `/list` command, builds inline keyboard, sends initial message
- New `_make_list_callback_handler(repository)` — handles `CallbackQuery` from inline button taps, parses `callback_data` (`year:2025` or `month:2025:3`), edits the message

**`main.py`**: Register `CommandHandler("list", ...)` and `CallbackQueryHandler(...)`.

### Callback Data Encoding

Button values encode state as string prefixes:
- `year:2026` → show year 2026 aggregate
- `month:2026:3` → show March 2026 detail

Single `CallbackQueryHandler` with pattern `r"^(year|month):"` dispatches both.

### Button Layout

- Year buttons: one row, ordered descending (current year first)
- Month buttons: one row, ordered chronologically (Jan → Dec)
- Month names abbreviated to 3 letters: Jan, Feb, Mar, ...
- No button for the same state (e.g., if viewing March, don't show a `[Mar]` button)

### Multi-User Isolation

Each handler reads `update.effective_user.id` and passes it to repository queries. No cross-user data leakage — same pattern as existing `/report`.

## BDD Feature Definition

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
    And the message shows the total "55.00 EUR"
    And the bot shows buttons labeled "Jul" and "Mar"
    And the bot shows a button labeled "2026"
    And the bot does not show a button labeled "2025"
    And the message explains that only months with expenses are shown

  @story-12
  Scenario: /list with no expenses shows informative message without buttons
    Given I have no expenses recorded
    When I send the command "/list"
    Then the bot replies with a message that no expenses are recorded
    And the bot does not show any month buttons
    And the bot does not show any year buttons

  @story-13
  Scenario: /list isolates expenses by user
    Given the following expenses exist:
      | amount | currency | merchant     | date       | user_id |
      | 50.00  | EUR      | User 123 Shop| 2026-07-01 | 123     |
      | 25.00  | EUR      | User 456 Shop| 2026-07-02 | 456     |
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
    And the message shows the total "30.00 EUR"

  @story-15
  Scenario: Tapping a year button switches to that year and shows year total
    Given the following expenses exist:
      | amount | currency | merchant    | date       | category |
      | 42.50  | EUR      | Supermarket  | 2026-07-10 | food     |
      | 30.00  | EUR      | Book Store   | 2026-03-05 | shopping |
      | 15.00  | EUR      | Old Shop     | 2025-12-01 | shopping |
    Given the list view for the current month is displayed
    When the user selects year "2025"
    Then the message shows the year total "15.00 EUR"
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

## Error Handling

- **Database errors**: exceptions propagate through the async handler chain and are caught by PTB's error handler (existing pattern)
- **Invalid callback_data**: `CallbackQueryHandler` with regex pattern silently ignores non-matching callbacks (PTB default behavior, no explicit handler needed)
- **Empty month**: `get_by_user_and_month` returns empty list → handled at the handler level with an informative message

## Testing Strategy

1. **BDD Behave tests**: feature file above, step definitions following existing `common_steps.py` + `report_steps.py` patterns
2. **Unit tests** (pytest): `test_sqlite_repository.py` for new query methods, `test_telegram_bot.py` for handler factory functions
3. **Sociable unit test boundaries**: mock PTB/Telegram API, use real repository (in-memory SQLite)

## Dependencies

No new dependencies. All required PTB classes (`InlineKeyboardButton`, `InlineKeyboardMarkup`, `CallbackQueryHandler`) are already available in the pinned `python-telegram-bot[job-queue]>=21.11` dependency.
