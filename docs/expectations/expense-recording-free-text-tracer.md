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

### Expectation-to-Test Mapping

| # | Expectation | Executed Evidence |
|---|---|---|
| 1 | Complete free text + `ONE_SHOT` → `ExpenseRecorded` | `tests/application/test_expense_recording.py::test_complete_text_records_expense[ONE_SHOT]` — 7 passed, 0 failed |
| 2 | Complete free text + `CONVERSATIONAL` + no pending Correction → `ExpenseRecorded` | `tests/application/test_expense_recording.py::test_complete_text_records_expense[CONVERSATIONAL]` — 7 passed, 0 failed |
| 3 | Telegram translates free-text → `RecordExpense` with correct fields; renders confirmation | `tests/adapters/inbound/test_telegram_bot.py::TestTextHandler::test_complete_extraction_calls_use_case_and_confirms` — 2 passed, 0 failed |
| 4 | CLI translates `extract-from-text` → `RecordExpense` with correct fields; prints result | `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_text_flow_translates_arguments_to_record_command`, `test_text_flow_prints_result_and_saves` — 9 passed, 0 failed |
| 5 | Incomplete Extraction in either mode → `ExtractionIncomplete`, not persisted | `tests/application/test_expense_recording.py::test_incomplete_text_returns_without_persisting[ONE_SHOT]`, `test_incomplete_text_returns_without_persisting[CONVERSATIONAL]` — 7 passed, 0 failed |
| 6 | Telegram incomplete → opens existing pending Correction state; renders missing-fields prompt | `tests/adapters/inbound/test_telegram_bot.py::TestTextHandler::test_partial_extraction_opens_existing_correction_state` — 2 passed, 0 failed |
| 7 | CLI incomplete → prints incomplete/not-saved output | `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_text_flow_renders_incomplete_without_saving` — 9 passed, 0 failed |
| 8 | Extraction and repository exceptions propagate from `ExpenseRecordingUseCase` | `tests/application/test_expense_recording.py::test_extraction_exception_propagates`, `test_repository_exception_propagates` — 7 passed, 0 failed |
| 9 | Telegram and CLI must not construct or save an Expense in migrated free-text paths | Confirmed by `test_complete_extraction_calls_use_case_and_confirms` (Telegram calls `recording.record()` — no `Expense` construction, no `repository.save()`). `test_text_flow_translates_arguments_to_record_command` (CLI calls `expense_recording.record()` — no direct construction). Both adapters delegate entirely to `ExpenseRecordingPort`. |
| 10 | Receipt-photo orchestration must not move behind `ExpenseRecordingPort` | Confirmed by `test_complete_extraction_saves_and_confirms` (PhotoHandler calls `extraction_adapter.extract()` + constructs `Expense` directly in `_respond_to_extraction`; receipt-photo orchestration remains on `ExtractionPort`/repository/`CorrectionStore` and outside `ExpenseRecordingPort`; rendering helper refactoring and logging test changes do not alter that ownership). `test_image_flow_does_not_use_expense_recording` (CLI image path uses legacy `extract→save` pipeline, no recording port imports). ARCH-001 remains `In progress`. |
| 11 | Text message with pending Correction → existing Correction handler, not new `RecordExpense` | `test_text_handler_with_pending_correction_refine_complete_saves_and_removes`, `test_text_handler_with_pending_correction_still_incomplete_asks_again`, `test_text_handler_with_pending_correction_maxed_out_removes_and_fails`, `test_text_handler_without_pending_correction_normal_flow` (telegram_bot.py — TestCorrectionFlow shows pending correction check at top of text handler before recording port call). |
| 12 | ARCH-001 must not be marked resolved by this tracer slice | Confirmed in `docs/architecture/hexagonal-alignment-todo.md` — ARCH-001 status remains `In progress`. No change to status in this slice. |

### Focused Evidence: Application Workflow Tests

```text
$ uv run pytest tests/application/test_expense_recording.py -q
.......                                                                  [100%]
7 passed in 0.02s
```

Test names: `test_complete_text_records_expense[ONE_SHOT]`, `test_complete_text_records_expense[CONVERSATIONAL]`, `test_incomplete_text_returns_without_persisting[ONE_SHOT]`, `test_incomplete_text_returns_without_persisting[CONVERSATIONAL]`, `test_extraction_exception_propagates`, `test_repository_exception_propagates`, `test_use_case_satisfies_expense_recording_port`

### Focused Evidence: Telegram Text Handler Tests

```text
$ uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestTextHandler -q
..                                                                       [100%]
2 passed in 0.02s
```

Test names: `test_complete_extraction_calls_use_case_and_confirms`, `test_partial_extraction_opens_existing_correction_state`

### Focused Evidence: CLI Extraction Tests

```text
$ uv run pytest tests/adapters/inbound/test_cli_extraction.py -q
.........                                                                [100%]
9 passed in 0.55s
```

Test names: `TestArgparseSetup::test_parse_extract_from_image`, `TestArgparseSetup::test_parse_extract_from_text`, `TestArgparseSetup::test_allows_custom_user_id_and_db`, `TestArgparseSetup::test_requires_subcommand`, `TestMainSociable::test_text_flow_prints_result_and_saves`, `TestMainSociable::test_image_flow_saves_to_database`, `TestMainSociable::test_text_flow_translates_arguments_to_record_command`, `TestMainSociable::test_text_flow_renders_incomplete_without_saving`, `TestMainSociable::test_image_flow_does_not_use_expense_recording`

### Full Verification Chain (pytest)

```text
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
51 files left unchanged
All checks passed!
All checks passed!
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/clt/PersonalProjects/expese-report-bot/.worktrees/expense-recording-free-text-tracer
configfile: pyproject.toml
testpaths: tests
plugins: typeguard-4.4.3, anyio-4.14.2
collected 189 items

tests/adapters/inbound/test_authorization.py ....................        [ 10%]
tests/adapters/inbound/test_cli_extraction.py .........                  [ 15%]
tests/adapters/inbound/test_logging_config.py .....                      [ 17%]
tests/adapters/inbound/test_telegram_bot.py ............................ [ 32%]
...............                                                          [ 40%]
tests/adapters/inbound/test_telegram_bot_logging.py ............         [ 47%]
tests/adapters/out/test_dspy_extraction.py .....................         [ 58%]
tests/adapters/out/test_dspy_extraction_logging.py ........              [ 62%]
tests/adapters/out/test_sqlite_repository.py ..........................  [ 76%]
tests/adapters/out/test_sqlite_repository_logging.py ......              [ 79%]
tests/application/test_expense_recording.py .......                      [ 83%]
tests/domain/test_correction_state.py ............                       [ 89%]
tests/domain/test_csv_generator.py ......                                [ 92%]
tests/domain/test_models.py ..........                                   [ 97%]
tests/ports/test_extraction.py ..                                        [ 98%]
tests/ports/test_repository.py ..                                        [100%]

============================= 189 passed in 8.33s ==============================
```

### Full Verification Chain (Behave)

```text
$ uv run behave
7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
Took 0min 1.293s
```

Behave features: authorization, cli_extraction, correction, delete, list, report, telegram_bot.

### ARCH-001 Status Confirmation

File: `docs/architecture/hexagonal-alignment-todo.md`
Field: `Status` for ARCH-001
Value: `In progress`

No changes were made to this file in this slice. The status remains `In progress`.
