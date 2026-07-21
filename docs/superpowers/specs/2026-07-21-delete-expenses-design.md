# Delete Saved Expenses — Design

**Date:** 2026-07-21  
**Status:** Approved for implementation planning  
**Scope:** Add user-facing deletion for already saved expenses in the Telegram bot.

## Goal

Users can remove mistakes from their records after an expense has already been saved.

The feature has two entry points:

1. `/delete <expense_id>` where `<expense_id>` is an easy-to-type integer.
2. A delete button shown under every successful expense creation confirmation.

## Decisions

### Expense IDs

Expense IDs become global auto-increment integers.

- `Expense.id` changes from `str | None` to `int | None`.
- `None` still means “not persisted yet”.
- SQLite assigns the integer ID on insert.
- Holes in the sequence are acceptable after deletion.
- No migration is required for existing development databases. The project is still in development, so existing UUID-based dev data may be reset manually.

### User-scoped lookup and deletion

All user-facing expense lookup and deletion is scoped by Telegram `user_id` at the repository boundary.

`/delete 42` means: delete expense `#42` from the current user’s records.

There is no separate “belongs to another user” case in behavior or wording. If no row matches the current `user_id` and requested `expense_id`, the result is simply not found.

### Deletion semantics

Deletion is a hard delete from the database.

After deletion:

- `/list` no longer shows the expense;
- `/report` no longer includes the expense;
- repository lookup for that user and ID returns not found.

The original Telegram confirmation message may remain in chat as an edited artifact, but the database row is removed.

### `/delete` command behavior

Valid command:

```text
/delete 42
```

Successful deletion replies with an audit-style summary:

```text
🗑️ Deleted expense #42: Supermarket — 42.50 EUR — 2026-07-10
```

If no expense matches the current user and ID:

```text
Expense #42 was not found.
```

Invalid formats all return the same usage message:

```text
Usage: /delete <expense_id>
```

Invalid formats include:

- `/delete`
- `/delete abc`
- `/delete 42 extra`
- non-positive IDs

### Delete button behavior

Every successful save confirmation gets a delete button.

This includes:

- complete receipt-photo extraction;
- complete free-text extraction;
- correction flow that becomes complete and saves an expense.

The confirmation message includes the assigned integer ID:

```text
📄 Extracted expense:
Expense #42
Amount: 42.50 EUR
Merchant: Supermarket
Date: 2026-07-10
Category: groceries

✅ Saved.
```

The inline keyboard contains one button:

```text
🗑️ Delete
```

Tapping the button immediately deletes the expense. There is no confirmation prompt and no undo flow in this slice.

After successful button deletion, the bot edits the original message instead of replacing it entirely:

- original details remain visible;
- original details are struck through;
- a deleted note is appended;
- the delete button is removed.

Example shape:

```text
<s>📄 Extracted expense:
Expense #42
Amount: 42.50 EUR
Merchant: Supermarket
Date: 2026-07-10
Category: groceries

✅ Saved.</s>

🗑️ Deleted.
```

Use Telegram HTML parse mode for strikethrough and escape dynamic text before formatting.

If the delete callback cannot find a matching expense for the current user, the bot answers the callback with a brief not-found message and leaves the original message unchanged.

### `/list` ID visibility

`/list` output should include integer expense IDs so users can later run `/delete <id>`.

Example line shape:

```text
#42  2026-07-10  Supermarket  42.50 EUR  groceries
```

`/list` does not get per-expense delete buttons in this slice. Its inline keyboard remains focused on year/month navigation.

### CSV report

CSV report output remains unchanged. Expense IDs are not added to CSV in this slice.

## Architecture

### Domain model

Update `Expense.id`:

```python
id: int | None
```

No Telegram, SQLite, or IO concerns enter the domain layer.

### Repository port

The repository port should expose user-scoped operations for user-facing ID lookup and deletion.

Conceptual shape:

```python
def get_by_id(self, user_id: int, expense_id: int) -> Expense | None:
    ...

def delete_by_id(self, user_id: int, expense_id: int) -> Expense | None:
    ...
```

`delete_by_id` returns the deleted `Expense` so the Telegram adapter can format the success reply after the row is removed.

### SQLite repository

Development-time schema change:

```sql
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    merchant TEXT NOT NULL,
    date TEXT NOT NULL,
    category TEXT,
    user_id INTEGER NOT NULL,
    receipt_photo_id TEXT,
    created_at TEXT NOT NULL
)
```

`save()` inserts without an explicit ID when `expense.id is None`, then uses `cursor.lastrowid` for the returned domain object.

`delete_by_id(user_id, expense_id)`:

1. selects the row with `WHERE id = ? AND user_id = ?`;
2. returns `None` if no row matches;
3. deletes with the same scoped predicate;
4. commits;
5. returns the pre-delete `Expense`.

### Telegram adapter

Add:

- `/delete` command handler;
- callback handler for delete button callbacks.

Callback data shape:

```text
delete:<expense_id>
```

This coexists with existing `/list` callback data (`year:` and `month:`).

Use small helpers for:

- saved-expense confirmation formatting;
- delete button keyboard creation;
- command-delete success formatting;
- struck-through deleted message formatting;
- parsing positive integer expense IDs.

## BDD feature definition

Keep the new feature focused on deletion-specific behavior. Reuse existing Gherkin vocabulary where possible and add only narrow delete-specific steps.

### New `features/delete.feature`

```gherkin
Feature: Delete Saved Expenses
  As a user
  I want to delete saved expenses by id or from the creation message
  So that I can remove mistakes from my records

  Background:
    Given the bot is running
    And the database is empty

  @story-17
  Scenario: /delete removes a saved expense and confirms what was deleted
    Given the following expenses exist:
      | id | amount | currency | merchant    | date       | category  |
      | 1  | 42.50  | EUR      | Supermarket | 2026-07-10 | groceries |
      | 2  | 12.50  | EUR      | Coffee Shop | 2026-07-15 | food      |
    When I send the command "/delete 2"
    Then the bot should reply with "Deleted expense #2: Coffee Shop — 12.50 EUR — 2026-07-15"
    And expense #2 should no longer be recorded

  @story-17
  Scenario: /delete reports not found for an expense outside my records
    Given the following expenses exist:
      | id | amount | currency | merchant       | date       | user_id |
      | 1  | 50.00  | EUR      | User 123 Shop  | 2026-07-10 | 123     |
      | 2  | 25.00  | EUR      | User 456 Shop  | 2026-07-11 | 456     |
    When user 123 sends the command "/delete 2"
    Then the bot should reply with "Expense #2 was not found."
    And expense #2 should still be recorded for user 456

  @story-17
  Scenario: Invalid /delete commands show the usage message
    When I send invalid delete commands:
      | command          |
      | /delete          |
      | /delete abc      |
      | /delete 42 extra |
    Then each delete command should reply with "Usage: /delete <expense_id>"

  @story-18
  Scenario: Delete button strikes through the original saved-expense message
    Given a saved confirmation for expense #1 exists:
      | id | amount | currency | merchant     | date       | category |
      | 1  | 3.50   | EUR      | Central Cafe | 2026-07-12 | food     |
    When I tap the delete button for expense #1
    Then the edited confirmation still contains "Central Cafe"
    And the edited confirmation shows struck-through expense details
    And the edited confirmation includes "🗑️ Deleted."
    And the delete button is removed from the edited confirmation
    And expense #1 should no longer be recorded
```

### Updates to existing feature files

Add minimal assertions where the behavior naturally belongs.

In `features/list.feature`, add ID visibility to the existing current-month list scenario:

```gherkin
And the message lists expense "#1" for merchant "Supermarket"
And the message lists expense "#2" for merchant "Coffee Shop"
```

In `features/telegram_bot.feature`, add delete button assertions to successful photo and text save scenarios:

```gherkin
And the bot should reply with a confirmation containing "Expense #1"
And the bot shows exactly these buttons: "🗑️ Delete"
```

In `features/correction.feature`, add the same assertions to the scenario where correction becomes complete and saves the expense:

```gherkin
And the bot should reply with a confirmation containing "Expense #1"
And the bot shows exactly these buttons: "🗑️ Delete"
```

### New step vocabulary

Extend existing `Given the following expenses exist:` to support optional `id` in the data table.

Add focused delete/list steps:

```gherkin
And expense #2 should no longer be recorded
And expense #2 should still be recorded for user 456
When I send invalid delete commands:
Then each delete command should reply with "Usage: /delete <expense_id>"
Given a saved confirmation for expense #1 exists:
When I tap the delete button for expense #1
Then the edited confirmation still contains "Central Cafe"
Then the edited confirmation shows struck-through expense details
Then the edited confirmation includes "🗑️ Deleted."
Then the delete button is removed from the edited confirmation
Then the message lists expense "#1" for merchant "Supermarket"
Then the message does not list expense "#2" for merchant "Coffee Shop"
```

## Expectations for implementation evidence

Create `docs/expectations/delete-expenses.md` before implementation.

It should cover:

- integer IDs are assigned and user-visible;
- `/delete <id>` hard-deletes a user-scoped expense;
- `/delete` invalid formats show usage;
- not-found uses simple user-scoped wording;
- creation confirmations include ID and delete button;
- delete button edits the original message with strikethrough plus deleted note;
- deleted rows disappear from list/report because they are hard-deleted;
- CSV output remains unchanged;
- no schema migration is attempted.

## Out of scope

- Per-expense delete buttons in `/list`.
- Undo delete.
- Delete confirmation prompt.
- Soft delete or audit table.
- CSV ID column.
- Migration from UUID development databases.
