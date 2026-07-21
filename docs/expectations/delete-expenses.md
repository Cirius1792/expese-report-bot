# Delete Saved Expenses — Expectations

## Happy Path

1. **Integer IDs are assigned and visible in /list.**
   - When an expense is saved, it receives an auto-increment integer id.
   - `/list` output shows ids in the format `#<id>` before each expense line.

2. **/delete <id> hard-deletes a user-scoped expense.**
   - `/delete 42` deletes expense #42 for the current Telegram user.
   - Successful deletion replies with: `🗑️ Deleted expense #42: <merchant> — <amount> <currency> — <date>`.
   - After deletion, `repository.get_by_id(42)` returns `None`.
   - Deleted expenses disappear from `/list` and `/report`.

3. **/delete invalid formats show usage.**
   - `/delete`, `/delete abc`, `/delete 42 extra`, `/delete 0` all reply: `Usage: /delete <expense_id>`.

4. **User-scoped delete: not-found for wrong user.**
   - User A's `/delete <id>` targeting user B's expense returns `Expense #<id> was not found.`
   - User B's expense remains intact.

5. **Save confirmations include integer ID and delete button.**
   - Complete photo extraction, complete free-text extraction, and successful correction all show `Expense #<id>` in the confirmation.
   - Each confirmation has exactly one inline button: `🗑️ Delete` with callback data `delete:<id>`.

6. **Delete button edits original message with strikethrough.**
   - Tapping the delete button edits the original confirmation message.
   - Original details remain visible wrapped in `<s>...</s>` (HTML strikethrough).
   - `🗑️ Deleted.` is appended after the struck-through content.
   - The delete button is removed from the edited message.
   - The expense is hard-deleted from the database.

## Edge Cases

7. **CSV output is unchanged.**
   - CSV report does not include an ID column.
   - CSV output is identical to before except for the expense data itself.

8. **No schema migration for existing dev databases.**
   - The schema uses `INTEGER PRIMARY KEY AUTOINCREMENT` instead of `TEXT PRIMARY KEY`.
   - Existing UUID-based dev databases are not migrated — manual reset acceptable.

9. **/list does not get per-expense delete buttons.**
   - The `/list` inline keyboard remains year/month navigation only.

10. **No confirmation prompt or undo.**
    - Delete button immediately deletes — no confirmation dialog.
    - There is no undo mechanism in this slice.

## Non-Behaviors

- Per-expense delete buttons are NOT present in `/list`.
- There is NO delete confirmation prompt.
- There is NO undo delete flow.
- CSV does NOT include an ID column.
- UUID dev databases are NOT migrated.

## Evidence Mapping

| Expectation | Evidence |
|-------------|----------|
| Integer IDs assigned | `test_save_assigns_id_when_none` (pytest) |
| IDs visible in /list | `test_format_month_view_includes_expense_ids` (pytest), list.feature ID assertions (behave) |
| /delete hard-deletes user-scoped | `TestDeleteHandler` tests (pytest), delete.feature (behave) |
| /delete invalid format usage | `test_delete_invalid_format_returns_usage` (pytest), delete.feature (behave) |
| User-scoped not-found | `test_delete_by_id_scoped_to_user` (pytest), delete.feature (behave) |
| Save confirmations with ID + button | `test_save_confirmation_includes_id_and_delete_button` (pytest), telegram_bot.feature + correction.feature (behave) |
| Delete button strikethrough edit | `TestDeleteCallbackHandler` (pytest), delete.feature @story-18 (behave) |
| CSV unchanged | `test_csv_generator.py` unchanged (pytest) |
| No schema migration | Manual verification — schema DDL uses AUTOINCREMENT, no migration code |
