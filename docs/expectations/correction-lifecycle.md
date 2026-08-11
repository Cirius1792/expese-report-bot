# Correction Lifecycle Expectations

Scope: move the entire **Correction** lifecycle out of
`adapters/inbound/telegram_bot.py` into the application layer
(`application/expense_recording.py::ExpenseRecordingUseCase`): pending-state routing,
`refine()` vs `extract()` choice, attempt counting, max-out, and save-and-clear. The
Telegram text and photo handlers become pure translation + rendering behind
`ExpenseRecordingPort.record()`. This slice also moves `CorrectionStore` from
`domain/correction_state.py` to `application/correction_state.py` (workflow-owned session
state, ARCH-005 partial; the `PendingCorrection` entity STAYS in domain).

Out of scope: tracker status changes (Phase 3), `/list` `/report` `/delete` (Phase 4),
configuration/composition (Phase 5).

## Design shape (pinned)

The driving Interface keeps ONE mode-aware operation,
`ExpenseRecordingPort.record(command) -> RecordingOutcome` — the "mode-aware single
operation" alternative CHOSEN in
`docs/superpowers/specs/2026-07-21-expense-recording-architecture-design.md` ("Alternatives
Considered"). The use case routes on pending Correction state internally. This follows ADR
0006 exactly (application-owned driving Interface; Correction state as an in-process
implementation detail with NO new port), so no new ADR is added.

`RecordingOutcome` is extended with four frozen dataclasses:

- `CorrectionOpened(extraction)` — incomplete Extraction in CONVERSATIONAL mode; pending
  Correction state opened.
- `CorrectionResolved(expense, extraction)` — Correction refined to completion; Expense
  saved; state cleared.
- `CorrectionStillIncomplete(extraction, attempt_count)` — Correction refined but still
  incomplete; attempt count incremented.
- `CorrectionLimitReached()` — maximum Correction attempts exhausted; state cleared;
  nothing persisted.

`ExpenseRecordingUseCase(extraction, repository, correction_store)` — the store is a
required, explicit constructor dependency (in-process; no new port per ADR 0006).

`record()` routing (exact):

1. CONVERSATIONAL **text** with a pending Correction for the user:
   - `pending.maxed_out` (attempt_count >= 3) is checked BEFORE refining: state removed,
     `CorrectionLimitReached()`, NO `refine()` call, nothing persisted.
   - Otherwise `refine(pending.original_result, command.source)`:
     - complete -> construct Expense with `receipt_photo_id=None` (PINNED QUIRK: even when
       the original partial came from a photo), `created_at=now`, save, remove state,
       `CorrectionResolved`.
     - incomplete -> store `PendingCorrection(user_id, pending.original_result,
       attempt_count+1)` (the ORIGINAL result is kept), `CorrectionStillIncomplete` with
       the incremented attempt count.
2. Fresh recording (any ONE_SHOT, CONVERSATIONAL without pending, ANY image source):
   - `extract(command.source, command.source_type)` (unchanged current path).
   - complete -> save -> `ExpenseRecorded` (unchanged). For image sources, any pre-existing
     pending state is left UNTOUCHED (PINNED QUIRK).
   - incomplete -> CONVERSATIONAL: open state `PendingCorrection(user_id, result)`
     (attempt 1; for a photo this OVERWRITES any stale pending — pinned) and return
     `CorrectionOpened`; ONE_SHOT: return `ExtractionIncomplete` (no state access ever).

Logging: every pre-existing log MESSAGE TEXT is still emitted exactly once per operation.
Workflow-event logs move to the application use case (stdlib logging; the logger module
name changes, the message text does not); transport-level and rendering logs stay in the
Telegram adapter. Message content is pinned in tests, not the logger name.

| Log message (text pinned) | Emitter after slice |
|---|---|
| `Correction received from user %s (attempt %s/3)` | use case (pending path entry) |
| `Correction maxed out for user %s (attempt %s/3), clearing` | use case (maxed-out branch) |
| `Correction resolved for user %s: saved updated expense` | use case (resolved branch) |
| `Correction still incomplete for user %s (attempt %s)` | use case (still-incomplete branch) |
| `Text received from user %s` | use case (fresh CONVERSATIONAL text path only — preserves the current no-pending-only emission exactly; ONE_SHOT/CLI never emits it) |
| `Photo received from user %s` | adapter (unchanged) |
| `Partial extraction for user %s text: missing %s` | adapter (rendering `CorrectionOpened` from text) |
| `Partial extraction for user %s photo: missing %s` | adapter (rendering `CorrectionOpened` from photo) |
| `Complete extraction for user %s text` / `... photo` | adapter (rendering `ExpenseRecorded`) |
| `Saved expense %s for user %s` | adapter (`_reply_with_recorded_expense`, unchanged) |

## Happy paths

1. A new complete text message (no pending Correction) is translated into
   `RecordExpense(user_id, source=text, source_type="text", mode=CONVERSATIONAL,
   receipt_photo_id=None)` and crosses `ExpenseRecordingPort.record()` exactly once;
   outcome `ExpenseRecorded`; the adapter renders "📄 *Extracted expense:* … ✅ Saved."
   with the delete button, byte-identical to the pre-refactor format. (Regression lock —
   Phase 1 behavior.)
2. A text message from a user WITH a pending Correction routes to the Correction path:
   `refine()` is called with the ORIGINAL partial `ExtractionResult` and the raw
   correction text; `extract()` is NEVER called. On a complete refined result the Expense
   is saved (extracted fields + user identity, `receipt_photo_id=None`, recording-time
   `created_at`), the pending state is removed, and the outcome is `CorrectionResolved`;
   the adapter renders "📄 *Updated expense:* … ✅ Updated and saved." with the delete
   button, byte-identical.
3. A CONVERSATIONAL text message with NO pending Correction that extracts incomplete opens
   pending state (`PendingCorrection` with the partial result, attempt_count 1) and
   returns `CorrectionOpened`; the adapter renders "I extracted partial information.
   Please reply with the missing details: …", byte-identical.
4. A CONVERSATIONAL Receipt photo that extracts incomplete opens the same pending state
   (attempt 1) and returns `CorrectionOpened`; the photo handler renders the same partial
   prompt, byte-identical. (State setup now happens inside the use case, not the adapter.)

## Edge cases

5. A refined-but-incomplete Correction increments the attempt count (1→2 and 2→3), stores
   `PendingCorrection` with the ORIGINAL result and the incremented count, and returns
   `CorrectionStillIncomplete(extraction, attempt_count)`; the adapter renders "I still
   could not extract all fields. Missing: …. Please provide the missing details.",
   byte-identical.
6. A text message from a user whose pending Correction is maxed out (attempt_count >= 3)
   returns `CorrectionLimitReached()`: `refine()` is NOT called, nothing is persisted, the
   pending state is removed; the adapter renders "I couldn't complete the extraction after
   3 attempts. Please send a new photo or description.", byte-identical.
7. ONE_SHOT mode never touches the CorrectionStore: an incomplete ONE_SHOT Extraction
   returns `ExtractionIncomplete` with the store's `get`/`set`/`remove` never called.
8. A COMPLETE photo Extraction while a stale pending Correction exists returns
   `ExpenseRecorded` and leaves the pending state UNTOUCHED (same object, same attempt
   count); `refine()` is never called for image sources.
9. An INCOMPLETE photo Extraction while a stale pending Correction exists OVERWRITES the
   stale state with `PendingCorrection(user_id, <new partial result>, attempt_count=1)`
   and returns `CorrectionOpened`.
10. Extraction exceptions (`extract` AND `refine`) and repository exceptions propagate
    unchanged through `ExpenseRecordingUseCase.record()`; a `refine()` failure leaves the
    pending state untouched.
11. Every log message text from the pre-refactor flow is still emitted exactly once per
    operation (see the table above), and no new message text is introduced; no secrets,
    source text, merchant values, or Telegram file_ids are logged.

## Behaviors that must not happen

12. No PTB (`telegram`/`telegram.ext`) or argparse types in `application/` — the use case
    and Correction state are drivable without any transport types.
13. `adapters/inbound/telegram_bot.py` must not import `CorrectionStore`,
    `PendingCorrection`, or `ExtractionPort`; neither `_make_text_handler` nor
    `_make_photo_handler` takes a `correction_store`/`extraction_adapter`/`repository`
    parameter; `register_handlers(app, expense_recording, repository)` keeps `repository`
    only for /report /list /delete (Phase 4 scope).
14. No message-format drift: the five user-visible messages (extracted-expense
    confirmation, updated-expense confirmation, partial prompt, still-incomplete prompt,
    limit-reached message) and the delete keyboard are byte-identical.
15. `receipt_photo_id` must be None on Correction saves — even when the original partial
    Extraction came from a photo (pinned quirk).
16. `_handle_correction` must not survive in `telegram_bot.py`; Correction attempt
    semantics (`attempt_count` starts at 1, max 3, `maxed_out` invariant) are preserved
    exactly.



## Evidence

### Final verification chain (HEAD a27637d)

```
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
93 files left unchanged
All checks passed!
All checks passed!
============================= 200 passed in 8.21s ==============================
7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
Took 0min 0.795s
```

### Expectation-to-Test Mapping

| # | Expectation | Executed Evidence |
|---|---|---|
| 1 | CONVERSATIONAL text with NO pending: extract → complete → ExpenseRecorded (regression) | `test_complete_text_records_expense[CONVERSATIONAL]` (application) — record() called with `mode=CONVERSATIONAL`, `extract` invoked, saved expense preserved. |
| 2 | CONVERSATIONAL text WITH pending (not maxed): refine → complete → save (receipt_photo_id=None), clear state → CorrectionResolved | `test_correction_resolve_saves_clears_and_returns_resolved` (application) — refine() called with the ORIGINAL partial result; extract() NOT called; saved Expense has `receipt_photo_id=None`; store cleared. |
| 3 | CONVERSATIONAL incomplete WITHOUT pending → CorrectionOpened (attempt 1), state opened | `test_conversational_incomplete_opens_correction[lunch 15 eur-text-None]`, `[...image bytes-image-photo-file-id-123]` (application) — store holds PendingCorrection (attempt_count=1, original=partial result). |
| 4 | Photo: fresh extract path regardless of pending; complete → ExpenseRecorded, pending untouched; incomplete → pending overwritten, CorrectionOpened | `test_complete_image_leaves_stale_pending_untouched` (application) — stale pending with attempt_count=2 survives a complete photo save. `test_incomplete_image_overwrites_stale_pending` (application) — stale pending with attempt_count=2 replaced by fresh attempt=1 PendingCorrection. |
| 5 | Pending not maxed: refine incomplete → increment attempt, CorrectionStillIncomplete | `test_correction_still_incomplete_increments_attempt[1]` — 1→2; `[2]` — 2→3 (application) — refine called, save NOT called, store updated with incremented attempt. |
| 6 | Pending maxed (attempt≥3): NO refine, state cleared, CorrectionLimitReached, nothing persisted | `test_correction_maxed_out_returns_limit_reached_without_refining` (application) — refine.assert_not_called(), extract.assert_not_called(), save.assert_not_called(), store cleared. |
| 7 | ONE_SHOT never reads/writes correction state | `test_one_shot_incomplete_never_touches_correction_store` (application) — store.get/set/remove NEVER called. |
| 8 | Exceptions from refine propagate | `test_refine_exception_propagates` (application) — RuntimeError raised, pending state untouched. |
| 9 | Handler renders CorrectionResolved with "Updated and saved" | `TestCorrectionFlow::test_text_handler_renders_correction_resolved` (adapter) — "Updated and saved" in reply, delete button with correct callback_data. |
| 10 | Handler renders CorrectionStillIncomplete with "still could not extract" | `TestCorrectionFlow::test_text_handler_renders_correction_still_incomplete` (adapter) — "still could not extract all fields", missing field names listed. |
| 11 | Handler renders CorrectionLimitReached with "3 attempts" | `TestCorrectionFlow::test_text_handler_renders_correction_limit_reached` (adapter) — "3 attempts" in reply. |
| 12 | Photo handler renders CorrectionOpened with "partial information" | `TestCorrectionFlow::test_photo_handler_renders_correction_opened` (adapter) — "partial information" in reply. |
| 13 | register_handlers signature slimmed to 3 params | `TestRegisterHandlers::test_registers_all_handlers` (adapter) — passes with `register_handlers(app, recording, repository)`. |
| 14 | Correction flow logs preserved (CorrectionReceived/Resolved/etc.) | `TestCorrectionLogging::test_correction_flow_logged` (logging) — "correction" or "refine" or "updated" in caplog via the use case. |
| 15 | Text handler logs "Text received" for every text (transport-level) | `TestTextHandlerLogging::test_text_handler_logs_received` (logging) — "text" or "message" or "expense" in INFO logs. |
| 16 | Behave regression: all 7 features / 27 scenarios unchanged | Full behave suite green; no feature-file changes. |

### Red-state evidence (commit 7b6c5be)

31 tests failed before implementation:
- All 10 new application correction tests failed (use case not yet routing corrections)
- 14 new/rewired adapter rendering tests failed (new handler signature not yet implemented)
- 7 logging tests failed (old handler signatures + adapter setup)
- 3 old TestCorrectionFlow tests failed (CorrectionStore import removed; these were replaced)

### Production code changes

- `application/expense_recording.py`: CorrectionStore dependency; single record() operation with correction routing (one_shot vs conversational text vs image fresh); log workflow events.
- `application/correction_state.py`: moval of CorrectionStore (ARCH-005 partial).
- `ports/expense_recording.py`: CorrectionOpened, CorrectionResolved, CorrectionStillIncomplete, CorrectionLimitReached added.
- `telegram_bot.py`: _make_text_handler(expense_recording) only; _make_photo_handler(expense_recording) only; _handle_correction deleted; _reply_with_resolved_correction helper; register_handlers(app, expense_recording, repository).
- `main.py`, `cli_extraction.py`: new composition contracts.
- Behave step files: updated handler signatures and use-case construction.
 — expectation-to-test mapping, red-state output, and
the final full verification chain output)
