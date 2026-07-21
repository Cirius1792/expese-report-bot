# Expense Recording Free-Text Tracer Expectations

## Happy paths

1. Given a complete free-text description and `ONE_SHOT` mode, Expense Recording extracts once, saves one Expense for the command's User, and returns `ExpenseRecorded` containing the saved Expense and Extraction.
2. Given a complete free-text description and `CONVERSATIONAL` mode with no pending Correction, the same application use case extracts once, saves one Expense, and returns `ExpenseRecorded`.
3. Telegram translates a new free-text message to `RecordExpense` with the Telegram User ID, `source_type="text"`, `mode=CONVERSATIONAL`, and no Receipt photo ID; it renders the existing save confirmation and delete button.
4. CLI translates `extract-from-text` to `RecordExpense` with the selected User ID, `source_type="text"`, `mode=ONE_SHOT`, and no Receipt photo ID; it prints the existing Extraction and saved-Expense output.

## Edge cases

5. An incomplete Extraction in either mode returns `ExtractionIncomplete` and is not persisted.
6. Telegram opens its existing pending Correction state when a new free-text command returns `ExtractionIncomplete`, then renders the existing missing-fields prompt.
7. CLI prints the existing incomplete/not-saved output when free text returns `ExtractionIncomplete`.
8. Extraction and repository exceptions propagate unchanged from `ExpenseRecordingUseCase`.

## Behaviors that must not happen

9. Telegram and CLI must not construct or save an Expense in their migrated free-text paths.
10. Receipt-photo orchestration must not move behind `ExpenseRecordingPort` in this slice.
11. A text message for a User who already has a pending Correction must continue through the existing Correction handler rather than starting a new `RecordExpense` command.
12. ARCH-001 must not be marked resolved by this tracer slice.

## Evidence

Populate at completion with the exact pytest test names and the final output of:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```
