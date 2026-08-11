# Expense Recording Photo Slice Expectations

Scope: route the Telegram **Receipt-photo** path and the CLI **`extract-from-image`** path through
the driving Interface `ExpenseRecordingPort.record()` (implemented by
`application/expense_recording.py::ExpenseRecordingUseCase`), deleting the duplicated legacy
extract→construct→save pipelines from both driving Adapters. After this slice, no driving Adapter
constructs an `Expense` or calls `ExpenseRepositoryPort.save()` on the recording path.

Out of scope: the Correction lifecycle (Phase 2), `/list` `/report` `/delete` (Phase 4),
configuration/composition (Phase 5). The tracker status of ARCH-001 is not changed in this slice.

## Happy paths

1. A complete Receipt photo sent in Telegram is translated into
   `RecordExpense(user_id=<telegram user id>, source=<downloaded image bytes>, source_type="image",
   mode=CONVERSATIONAL, receipt_photo_id=<largest photo's Telegram file_id>)` and crosses
   `ExpenseRecordingPort.record()` exactly once. The outcome is `ExpenseRecorded`; the saved
   Expense keeps the Telegram `file_id` as `receipt_photo_id`; the Adapter renders the existing
   save confirmation ("📄 *Extracted expense:* … ✅ Saved.") with the delete button, byte-identical
   to the pre-refactor format.
2. CLI `extract-from-image IMAGE_PATH` is translated into
   `RecordExpense(user_id=<--user-id>, source=<file bytes>, source_type="image", mode=ONE_SHOT,
   receipt_photo_id=None)` crossing the same `ExpenseRecordingPort.record()` exactly once. The CLI
   prints the existing extraction output plus the "Saved expense: …" line verbatim.

## Edge cases

3. An incomplete photo Extraction returns `ExtractionIncomplete`; NOTHING is persisted. Telegram
   sets the pending `PendingCorrection` (attempt_count 1, original result) in the existing
   `CorrectionStore` and renders the existing missing-fields prompt ("I extracted partial
   information…"); CLI prints the existing "Extraction incomplete — not saved." output.
4. Extraction exceptions and repository exceptions propagate unchanged through
   `ExpenseRecordingUseCase.record()` for image commands.

## Behaviors that must not happen

5. Neither driving Adapter constructs an `Expense` nor calls `ExpenseRepositoryPort.save()` on the
   photo recording path (`_make_photo_handler`, CLI `extract-from-image`).
6. `_respond_to_extraction` orchestration (extract→check→construct→save) must not survive in
   `telegram_bot.py`.
7. No change to PTB file download calls (`bot.get_file`, `download_as_bytearray`), message texts,
   keyboards, callback data, or CLI stdout format.
8. No change to the Correction flow (`_handle_correction`, correction routing in
   `_make_text_handler`) — the partial-photo `PendingCorrection` setup stays in the Adapter
   verbatim until Phase 2.
9. The photo path must not open a `PendingCorrection` on complete Extraction, and must not skip
   the pending-correction setup on incomplete Extraction.

## Evidence

### Expectation-to-Test Mapping

| # | Expectation | Executed Evidence |
|---|---|---|
| 1 | Telegram photo → exact `RecordExpense` (CONVERSATIONAL, image bytes, Telegram `file_id` as `receipt_photo_id`) → `ExpenseRecorded`; confirmation + delete button rendered byte-identical | `tests/adapters/inbound/test_telegram_bot.py::TestPhotoHandler::test_complete_extraction_records_and_confirms` — asserts `record()` called once with the exact command and `context.bot.get_file` awaited with the largest photo's `file_id`; renders "✅ Saved." with amount/currency/merchant. `tests/adapters/inbound/test_telegram_bot.py::TestSaveConfirmation::test_save_confirmation_includes_id_and_delete_button` — "Expense #42" + "✅ Saved." + delete button `callback_data="delete:42"`. `tests/application/test_expense_recording.py::test_complete_image_records_expense_with_receipt_photo_id[CONVERSATIONAL]` — saved Expense keeps `receipt_photo_id="photo-file-id-123"`. Behave: `features/telegram_bot.feature` @story-3 "Send receipt photo with complete extraction" (unchanged feature file, green). |
| 2 | CLI `extract-from-image` → exact `RecordExpense` (ONE_SHOT, file bytes, `receipt_photo_id=None`) → prints existing extraction + saved-expense output | `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_image_flow_translates_arguments_to_record_command` — `record()` called once with the exact command. `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_image_flow_saves_to_database` — sociable test with real `SqliteExpenseRepository` + real `DspyExtractionAdapter` (boundaries mocked), asserts printed output and the persisted row. Behave: `features/cli_extraction.feature` @story-1 "Extract expense from receipt image via CLI" (unchanged feature file, green). |
| 3 | Incomplete photo Extraction → `ExtractionIncomplete`, nothing persisted; Telegram sets pending `PendingCorrection` + missing-fields prompt; CLI prints not-saved | `tests/application/test_expense_recording.py::test_incomplete_image_returns_without_persisting[ONE_SHOT]` and `[CONVERSATIONAL]` — no `repository.save`. `tests/adapters/inbound/test_telegram_bot.py::TestPhotoHandler::test_partial_extraction_asks_for_missing` — real `CorrectionStore` holds `PendingCorrection` (attempt_count 1, original result) and the reply lists exactly the missing fields. `tests/adapters/inbound/test_telegram_bot.py::TestCorrectionFlow::test_photo_handler_partial_extraction_creates_pending_correction`. `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_image_flow_renders_incomplete_without_saving` — byte-exact stdout and `save.assert_not_called()`. |
| 4 | Extraction/repository exceptions propagate unchanged | `tests/application/test_expense_recording.py::test_extraction_exception_propagates`, `tests/application/test_expense_recording.py::test_repository_exception_propagates` — `record()` is source-type-generic; the image application tests above exercise the same code path with `source_type="image"`. |
| 5 | No driving Adapter constructs `Expense` or calls `repository.save()` on the photo path | **Structural:** `_make_photo_handler(expense_recording, correction_store)` no longer receives the extraction adapter or the repository at all; CLI `main()` holds no repository reference outside the use case. **Executed:** all photo/CLI adapter tests inject a mocked `ExpenseRecordingPort` / patched `ExpenseRecordingUseCase` and pass — any direct `extract()`/`save()` call would fail the exact-command and no-save assertions (`test_partial_extraction_asks_for_missing`, `test_image_flow_renders_incomplete_without_saving`). **Source:** `grep` of `_make_photo_handler` and `cli_extraction.py` shows no `Expense(`, no `.save(`, no `.extract(`. |
| 6 | `_respond_to_extraction` orchestration must not survive | Deleted from `src/expense_report/adapters/inbound/telegram_bot.py`; the full suite (194 passed) runs without it. |
| 7 | No change to PTB download, message texts, keyboards, CLI stdout | `context.bot.get_file.assert_awaited_once_with("photo-abc-123")` in `test_complete_extraction_records_and_confirms`; byte-exact stdout assertions in `test_image_flow_renders_incomplete_without_saving` and `test_text_flow_prints_result_and_saves`; keyboard assertions in `test_save_confirmation_includes_id_and_delete_button`; all 27 behave scenarios green with zero `.feature` file changes. |
| 8 | No change to the Correction flow | `_handle_correction` and the correction routing in `_make_text_handler` untouched by the implementation diff; `TestCorrectionFlow` text tests and `tests/adapters/inbound/test_telegram_bot_logging.py` correction logging tests unmodified and green; `features/correction.feature` green. |
| 9 | Photo path pending-correction semantics | `tests/adapters/inbound/test_telegram_bot.py::TestCorrectionFlow::test_photo_handler_complete_extraction_no_pending_correction` — complete outcome stores nothing. `test_photo_handler_partial_extraction_creates_pending_correction` — incomplete outcome stores `PendingCorrection`. |

### Red-State Evidence (step 2, before implementation)

New/rewritten tests failed against the legacy implementation; everything else passed:

```text
FAILED tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_image_flow_translates_arguments_to_record_command
FAILED tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_image_flow_renders_incomplete_without_saving
FAILED tests/adapters/inbound/test_telegram_bot.py::TestPhotoHandler::test_complete_extraction_records_and_confirms
FAILED tests/adapters/inbound/test_telegram_bot.py::TestPhotoHandler::test_partial_extraction_asks_for_missing
FAILED tests/adapters/inbound/test_telegram_bot.py::TestSaveConfirmation::test_save_confirmation_includes_id_and_delete_button
FAILED tests/adapters/inbound/test_telegram_bot.py::TestCorrectionFlow::test_photo_handler_partial_extraction_creates_pending_correction
FAILED tests/adapters/inbound/test_telegram_bot.py::TestCorrectionFlow::test_photo_handler_complete_extraction_no_pending_correction
FAILED tests/adapters/inbound/test_telegram_bot_logging.py::TestPhotoHandlerLogging::test_photo_handler_logs_received
FAILED tests/adapters/inbound/test_telegram_bot_logging.py::TestPhotoHandlerLogging::test_photo_handler_logs_partial_extraction
FAILED tests/adapters/inbound/test_telegram_bot_logging.py::TestPhotoHandlerLogging::test_photo_handler_logs_saved_once
10 failed, 184 passed in 8.32s
```

(Application-level image tests `test_complete_image_records_expense_with_receipt_photo_id` and
`test_incomplete_image_returns_without_persisting` passed immediately, as expected — the use case
was already source-type-generic; they act as regression locks. `uv run behave` at the red commit:
7 features / 27 scenarios passed, since step files were updated with the implementation.)

### Focused Evidence: Application Image Tests

```text
$ uv run pytest tests/application/test_expense_recording.py -q
...........                                                              [100%]
11 passed in 0.03s
```

### Full Verification Chain (final, at the refactor commit)

```text
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
91 files left unchanged
All checks passed!
All checks passed!
============================= test session starts ==============================
platform linux -- Python 3.12.11, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/clt/Projects/expense-report-bot/.worktrees/hexagonal-alignment
configfile: pyproject.toml
testpaths: tests
plugins: typeguard-4.4.3, anyio-4.14.2
collected 194 items

tests/adapters/inbound/test_authorization.py ....................        [ 10%]
tests/adapters/inbound/test_cli_extraction.py ..........                 [ 15%]
tests/adapters/inbound/test_logging_config.py .....                      [ 18%]
tests/adapters/inbound/test_telegram_bot.py ............................ [ 32%]
...............                                                          [ 40%]
tests/adapters/inbound/test_telegram_bot_logging.py ............         [ 46%]
tests/adapters/out/test_dspy_extraction.py .....................         [ 57%]
tests/adapters/out/test_dspy_extraction_logging.py ........              [ 61%]
tests/adapters/out/test_sqlite_repository.py ..........................  [ 74%]
tests/adapters/out/test_sqlite_repository_logging.py ......              [ 77%]
tests/application/test_expense_recording.py ...........                  [ 83%]
tests/domain/test_correction_state.py ............                       [ 89%]
tests/domain/test_csv_generator.py ......                                [ 92%]
tests/domain/test_models.py ..........                                   [ 97%]
tests/ports/test_extraction.py ..                                        [ 98%]
tests/ports/test_repository.py ..                                        [100%]

============================= 194 passed in 8.03s ==============================
7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
Took 0min 0.629s
```

Behave features: authorization, cli_extraction, correction, delete, list, report, telegram_bot —
zero `.feature` file changes in this slice.
