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

_To be filled at step 4 with executed command output and test names._
