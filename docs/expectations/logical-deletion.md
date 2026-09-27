# Logical Deletion of Expenses — Expectations

> Supersedes the physical-delete behavior described in `delete-expenses.md`
> (expectations 2, 6, and the "hard-deletes" statements). The user-facing
> contract of `/delete`, the delete button, `/list`, `/report`, and CSV is
> unchanged — only the storage mechanism changes.

## Concept

Expenses are never physically removed from the `expenses` table. Instead each
`Expense` gains a `deleted_at: datetime | None` field. A row with a non-null
`deleted_at` is **logically deleted** and must be filtered out of every
user-facing data access. Rows can still be retrieved on demand via an opt-in
`include_deleted` flag on the port (used only by internal/audit paths).

## Design decisions (agreed)

1. **`deleted_at` timestamp.** `Expense` gains `deleted_at: datetime | None`.
   `None` means "not deleted". A timestamp (not a bool) is chosen so the
   deletion moment is auditable and to mirror the existing `created_at`.
2. **Opt-in retrieval of deleted rows.** Every read method on
   `ExpenseRepositoryPort` gains an optional `include_deleted: bool = False`
   parameter. Default `False` → deleted rows are filtered. Internal/audit paths
   pass `include_deleted=True`.
3. **`get_by_id` follows the same rule.** It is tests-only today, but is part of
   the storage contract, so it also carries `include_deleted` and defaults to
   filtering deleted rows.
4. **`delete_by_id` keeps its signature and becomes logical.** It now performs an
   `UPDATE ... SET deleted_at = ?` instead of a `DELETE`, and still returns the
   deleted `Expense` for the success message. No application-layer caller changes.
5. **Filtering lives in the driven adapter.** The SQLite queries add
   `AND deleted_at IS NULL` (or `IS NOT NULL` for the opt-in path). The
   application layer needs no read-path changes — this is the hexagonal win.
6. **Schema migration.** Existing tables are migrated with
   `ALTER TABLE expenses ADD COLUMN deleted_at TEXT` (nullable → existing rows
   read as "not deleted"). No row-level backfill required.
7. **Interaction with user-scoped ids (ADR 0010).** The single-statement INSERT
   that derives the `YYYYMMDD-n` key counts **soft-deleted rows too**, so keys
   become permanently unique per `(user_id, user_key)`. This is the reason logical
   deletion is a blocking dependency of issue #16.

## Affected layers (hexagonal)

| Layer | Change |
|---|---|
| `domain/models.py` | `Expense` gains `deleted_at: datetime \| None`. |
| `ports/repository.py` | Read methods gain `include_deleted: bool = False`; `delete_by_id` semantics change to logical. |
| `adapters/out/sqlite_repository.py` | Schema migration + per-query `deleted_at` filtering; `save` persists `deleted_at`; `delete_by_id` becomes an `UPDATE`. |
| `application/expense_queries.py` | No read-path changes. `delete_expense` unchanged (delegates to the port). |
| `application/expense_recording.py` | `_build_expense` sets `deleted_at=None` for fresh expenses. |
| `adapters/inbound/telegram_bot.py` | No user-facing change. Deleted rows simply vanish from listings. |
| `domain/csv_generator.py` | No change — it receives already-filtered expenses. |

## Acceptance criteria

### Happy path

- [ ] Saving a new expense leaves `deleted_at` as `None`.
- [ ] `/delete <id>` soft-deletes the expense: the row remains in the table with
      `deleted_at` set, and the user still sees the success message
      `🗑️ Deleted expense #<id>: <merchant> — <amount> <currency> — <date>`.
- [ ] The soft-deleted expense disappears from `/list` and `/report` and from the
      CSV report without any listing-code change.
- [ ] `/list` totals and month discovery exclude soft-deleted expenses.
- [ ] A soft-deleted expense is still retrievable via the port with
      `include_deleted=True` (e.g. for an audit/restore path).

### Edge cases

- [ ] `include_deleted=False` (default) on every read method filters deleted rows.
- [ ] `include_deleted=True` returns deleted rows too.
- [ ] A wrong-user `/delete` still returns "not found" (user scoping preserved).
- [ ] Soft-deleting does not reuse the row's id or disturb sibling rows.
- [ ] Existing databases migrate cleanly: pre-existing rows read as not-deleted.

### Must NOT happen

- [ ] No `DELETE FROM expenses` statement exists anywhere in the codebase.
- [ ] User-facing output never changes because of the internal switch to logical deletion.
- [ ] The domain layer gains any framework/IO import.
- [ ] `deleted_at` is rendered to users in any message, listing, or CSV.

## Evidence mapping

| Expectation | Test location |
|---|---|
| deleted_at persisted as None on save | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_save_leaves_deleted_at_none` |
| logical delete via UPDATE, row retained | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_delete_by_id_soft_deletes_row_retained` |
| reads filter deleted rows by default | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_get_by_id_filters_deleted_by_default`, `::test_get_by_user_and_month_filters_deleted_by_default`, `::test_get_months_with_expenses_excludes_deleted`, `::test_get_total_by_user_and_year_excludes_deleted` |
| include_deleted opt-in returns deleted rows | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_get_by_id_include_deleted_returns_deleted`, `::test_get_by_user_and_month_include_deleted_returns_all` |
| user scoping preserved on delete | `tests/adapters/out/test_sqlite_repository.py::TestDeleteById::test_delete_by_id_scoped_to_user` |
| already-deleted delete returns not-found | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_delete_already_deleted_returns_none` |
| soft-delete does not disturb siblings | `tests/adapters/out/test_sqlite_repository.py::TestLogicalDeletion::test_soft_delete_does_not_disturb_siblings` |
| application layer unchanged | `tests/application/test_expense_queries.py` (all passing, no edits) |
| schema migration | `tests/adapters/out/test_sqlite_repository.py::TestSchemaMigration::test_existing_db_without_deleted_at_migrates` |
| no `DELETE FROM expenses` remains | `grep -rn "DELETE FROM" src tests` → no matches |
| user-scoped key counts soft-deleted rows | deferred to issue #16 / ADR 0010 (key-count INSERT does not exist yet) |
