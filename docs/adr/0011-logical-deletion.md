# ADR 0011: Logical Deletion of Expenses

**Date:** 2026-07-19
**Status:** Accepted

## Context

Expenses are currently removed from the `expenses` table with a physical
`DELETE FROM expenses WHERE id = ? AND user_id = ?` (`sqlite_repository.py`,
invoked via `ExpenseQueryUseCase.delete_expense`). Physical deletion has two
downsides:

1. It is irreversible — no audit trail of when or why an expense was removed.
2. It breaks the user-scoped id feature (ADR 0010): while deletion is physical,
   a user who deletes their last expense for a date can cause that date's next
   expense to reuse the same `YYYYMMDD-n` key, so keys are not permanently
   unique. ADR 0010 explicitly lists logical deletion as a **blocking
   dependency**.

## Decision

Replace physical deletion with **logical deletion**:

- `Expense` gains a `deleted_at: datetime | None` field (`None` = not deleted).
- `delete_by_id(user_id, expense_id)` keeps its signature but now performs an
  `UPDATE expenses SET deleted_at = ? WHERE id = ? AND user_id = ?` instead of a
  `DELETE`, returning the pre-update row for the success message.
- Every **read** method on `ExpenseRepositoryPort` gains an optional
  `include_deleted: bool = False` parameter. The default filters logically
  deleted rows; internal/audit paths opt in with `include_deleted=True`.
- Filtering is implemented in the driven SQLite adapter (`AND deleted_at IS
  NULL`), so the application layer needs **no** read-path changes — the port
  contract stays stable.
- The `expenses` table is migrated with
  `ALTER TABLE expenses ADD COLUMN deleted_at TEXT` (nullable), so existing rows
  read as "not deleted" with no row-level backfill.
- The single-statement INSERT that derives the `YYYYMMDD-n` key (ADR 0010) counts
  **soft-deleted rows too**, making keys permanently unique per
  `(user_id, user_key)`.

## Consequences

- Deletes become reversible/auditable (the row and its timestamp persist).
- `/delete`, the inline delete button, `/list`, `/report`, and CSV keep the same
  user-facing behavior — deleted rows simply disappear from listings.
- No `DELETE FROM expenses` remains in the codebase.
- The port contract grows one optional parameter per read method; implementations
  must honor it. `delete_by_id` signature is unchanged.
- ADR 0010 (user-scoped ids) now depends on this ADR being implemented first.
- `Expense` construction sites (`_build_expense`, `_row_to_expense`, tests) must
  supply `deleted_at`.

## Out of scope

- Restoring soft-deleted expenses (future follow-up).
- Backfill/migration of user-scoped keys for existing expenses (ADR 0010 follow-up).
- Changing any user-facing message, listing format, or CSV schema.
