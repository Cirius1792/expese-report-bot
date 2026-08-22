# PDF Source Normalization Expectations

Scope: accept receipt **PDFs** (1–5 pages) as expense sources in parallel with photos and
free text, by introducing source normalization as a separate driven capability. The
approved design (Option B): a new driven port `SourcePreparationPort` converts a raw
upload into a neutral `SourceView`; the **existing** `ExpenseRecordingUseCase` is reused
and now explicitly orchestrates `prepare()` → `extract()`. One PDF = exactly one expense
(multi-page = one long invoice). PDFs with more than 5 pages are **rejected** — the user
must be told their request will not be satisfied (no silent truncation).

New contract pieces (implementation must match these names/shapes):

- `domain/source_types.py` — `class SourceType(Enum)`: `TEXT = "text"`, `IMAGE = "image"`, `PDF = "pdf"`.
- `ports/source_preparation.py`:
  - `@dataclass(frozen=True) FreeTextSourceView: text: str`
  - `@dataclass(frozen=True) ReceiptPagesSourceView: page_images: tuple[bytes, ...]`
  - `SourceView = FreeTextSourceView | ReceiptPagesSourceView`
  - `class SourcePreparationError(Exception)` — carries a user-facing `message: str`
  - `@runtime_checkable class SourcePreparationPort(Protocol)`: `prepare(source: str | bytes, source_type: SourceType) -> SourceView`
- `ports/extraction.py` — `extract(self, source: SourceView) -> ExtractionResult` (narrowed;
  `refine` unchanged).
- `ports/expense_recording.py` — `RecordExpense.source_type: SourceType`; new outcome
  `@dataclass(frozen=True) SourceRejected: reason: str` added to the `RecordingOutcome` union.
- `application/expense_recording.py` — constructor `(preparation, extraction, repository,
  correction_store)`; fresh path calls `prepare()` then `extract()`; `SourcePreparationError`
  is caught and mapped to `SourceRejected(reason=str(exc.message))`.
- `adapters/out/source_preparation.py` — `SourcePreparationAdapter`: `match source_type`
  dispatch (the strategy). TEXT → `FreeTextSourceView`; IMAGE → `ReceiptPagesSourceView` with
  the single original byte string (no decode/resize); PDF → pypdfium2 renders each page
  (scale 2, JPEG quality 92) in page order → `ReceiptPagesSourceView`. PDF with >5 pages, a
  0-page PDF, or invalid PDF bytes → `SourcePreparationError`.
- `adapters/out/dspy_extraction.py` — `extract` branches on `SourceView`: `FreeTextSourceView`
  → existing dSPy ChainOfThought path (unchanged); `ReceiptPagesSourceView` → **one** vision
  request containing 1..N image parts (per-page resize to 1536 + base64 stays here), prompt
  states the images are the pages of one receipt and requires a single JSON object.
- `adapters/inbound/telegram_bot.py` — new `MessageHandler(filters.Document.PDF, ...)` :
  download bytes → `RecordExpense(source_type=SourceType.PDF, mode=CONVERSATIONAL,
  receipt_photo_id=None)`. Complete → existing save confirmation + delete button.
  Incomplete → existing missing-fields prompt + pending correction (same as photo).
  `SourceRejected` → explicit rejection reply containing the actual page count and the 5-page
  limit. `WELCOME_MESSAGE` mentions that PDFs are accepted. Photo/text handlers switch the
  literal to the enum; their rendered output is byte-identical to before.
- `adapters/inbound/cli_extraction.py` — new `extract-from-pdf PDF_PATH` subcommand
  (ONE_SHOT); existing subcommands switch to the enum. `SourceRejected` → print the reason
  and exit with code 1.
- `adapters/inbound/main.py` — wire `SourcePreparationAdapter()` into the use case.
- `pyproject.toml` — add `pypdfium2` to runtime dependencies (`uv add pypdfium2`).
- `docs/adr/0008-pdf-source-normalization.md` — records the decision and rejected alternatives.

Out of scope: PDF size (bytes) caps; multi-expense-per-PDF; DOCX/other formats;
correction-flow changes; repository/query changes; new behave `.feature` scenarios
(existing features must stay green without modification).

## Happy paths

1. A Telegram user sends a PDF with 1–5 pages. The bot downloads the bytes and crosses
   `ExpenseRecordingPort.record()` exactly once with
   `RecordExpense(user_id=<id>, source=<pdf bytes>, source_type=SourceType.PDF,
   mode=CONVERSATIONAL, receipt_photo_id=None)`. The use case calls
   `preparation.prepare(source, SourceType.PDF)` (pages rendered in order), then
   `extraction.extract(view)` with a single `ReceiptPagesSourceView` whose `page_images`
   tuple has one entry per PDF page. Complete extraction → `ExpenseRecorded`; the saved
   Expense has `receipt_photo_id=None`; the standard save confirmation ("📄 *Extracted
   expense:* … ✅ Saved.") with the delete button is rendered.
2. One PDF always yields at most one expense: an N-page PDF produces exactly one vision
   request and at most one `Expense`, with the prompt instructing that all pages belong to
   the same receipt.
3. CLI `extract-from-pdf PDF_PATH` crosses `record()` exactly once with
   `RecordExpense(user_id=<--user-id>, source=<pdf bytes>, source_type=SourceType.PDF,
   mode=ONE_SHOT, receipt_photo_id=None)`, and prints the existing extraction output plus
   the "Saved expense: …" line for a complete result.
4. Existing paths are behaviorally unchanged: Telegram photo, Telegram text (fresh and
   correction routing), and CLI `extract-from-image` / `extract-from-text` produce the same
   messages, outcomes, and persisted data as before, with only the `source_type` literal
   replaced by the enum value.

## Edge cases

5. Boundary: a 5-page PDF is accepted and renders exactly 5 ordered page images.
6. A PDF with more than 5 pages is rejected: `prepare` raises `SourcePreparationError`
   naming the page count and the limit; the use case returns `SourceRejected` **without
   calling `extract()` and without persisting anything**. Telegram replies with a clear
   "not satisfied" message containing the actual page count and the 5-page limit. CLI
   prints the reason and exits with code 1. No page is silently dropped.
7. Invalid/corrupt PDF bytes (and a 0-page PDF) are rejected via the same
   `SourcePreparationError` → `SourceRejected` path with an understandable message.
8. An incomplete extraction from a PDF in CONVERSATIONAL mode returns `CorrectionOpened`
   and stores the pending correction, rendered with the existing missing-fields prompt —
   identical semantics to the photo path. In ONE_SHOT mode (CLI) it returns
   `ExtractionIncomplete` and persists nothing.
9. `FreeTextSourceView` text extraction and the correction `refine()` flow are byte-for-byte
   the same behavior as before (dSPy ChainOfThought path untouched except the entry signature).

## Behaviors that must not happen

10. No framework/IO import in `domain/`: `domain/source_types.py` is a plain enum;
    pypdfium2, PIL, telegram, dspy, and openai are imported only in adapters.
11. `SourceView` never carries base64, OpenAI chat parts, PDFium objects, or resize/model
    metadata: the ports boundary holds free text or raw ordered page-image bytes only.
12. No inbound adapter renders PDFs, resizes images, or imports pypdfium2/PIL on the
    recording path; inbound adapters remain pure translators of Telegram/CLI input into
    `RecordExpense`.
13. The extraction adapter does not count PDF pages, enforce the 5-page cap, or branch on
    `SourceType` — it only consumes a `SourceView`.
14. No new driving port, no new use case, and no per-type preparation ports (there is
    exactly one `SourcePreparationPort`).
15. Correction routing stays text-only: an image or PDF command never enters the
    `refine()` path on the fresh recording flow (incomplete → pending state only).
16. No page of an accepted PDF is dropped or reordered; rendering preserves page order.
17. No changes to repository/query logic, message keyboards, callback data, or the existing
    photo/text message texts; no `.feature` file changes.

## Evidence

### Expectation-to-Test Mapping

All test ids below executed via `uv run pytest` (268 passed) and `uv run behave`
(27 scenarios) against the final tree; see the full chain output at the bottom.

| # | Expectation | Executed Evidence |
|---|---|---|
| 1 | Telegram PDF happy path: one `record()` with `RecordExpense(source_type=SourceType.PDF, mode=CONVERSATIONAL, receipt_photo_id=None)`; prepare → extract(Single ReceiptPagesSourceView with one entry per page); saved expense `receipt_photo_id=None`; standard save confirmation + delete button | `tests/adapters/inbound/test_telegram_bot.py::TestPdfHandler::test_complete_extraction_records_and_confirms` (download by file_id, RecordExpense pdf/bytes/CONVERSATIONAL/receipt_photo_id=None, reply contains "✅ Saved."); `tests/application/test_expense_recording.py::test_pdf_complete_records_expense_with_receipt_photo_id_none` (`prepare.assert_called_once_with(pdf_bytes, SourceType.PDF)`, `extract.assert_called_once_with(pages)`, saved Expense `receipt_photo_id is None`); `tests/adapters/out/test_source_preparation.py::TestPdfPreparation::test_pdf_one_page_renders_single_jpeg_image` |
| 2 | One PDF → exactly one expense, exactly one vision request with 1..N image parts, prompt states pages belong to one receipt | `tests/adapters/out/test_dspy_extraction.py::TestExtractImage::test_extract_multi_page_uses_one_request_with_n_image_parts` (`create_call.call_count == 1`, 3 `image_url` parts, text part contains "one receipt" and "one json object"); `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_pdf_flow_prints_result_and_saves` (one create call, 2 image parts, exactly 1 DB row for a 2-page PDF) |
| 3 | CLI `extract-from-pdf` crosses `record()` once with ONE_SHOT / `receipt_photo_id=None`; prints extraction output + "Saved expense:" line | `tests/adapters/inbound/test_cli_extraction.py::TestMainSociable::test_pdf_flow_translates_arguments_to_record_command` (exact `RecordExpense` assert) and `test_pdf_flow_prints_result_and_saves` (real pypdfium2 render of a Pillow-generated 2-page PDF, "Saved expense:" in stdout, persisted row) |
| 4 | Existing paths behaviorally unchanged (photo/text handlers and CLI image/text; only the literal → enum) | `tests/adapters/inbound/test_telegram_bot.py::TestPhotoHandler::test_complete_extraction_records_and_confirms`, `TestTextHandler::test_complete_extraction_calls_use_case_and_confirms` (exact confirmation text), `test_partial_extraction_renders_partial_prompt` (byte-identical prompt), `test_cli_extraction.py::test_text_flow_prints_result_and_saves` / `test_image_flow_saves_to_database` (exact stdout + DB); behave: 7 features / 27 scenarios pass with zero `.feature` changes |
| 5 | Boundary: 5-page PDF accepted, renders exactly 5 ordered page images | `tests/adapters/out/test_source_preparation.py::TestPdfPreparation::test_pdf_five_pages_accepted_and_renders_five_images` |
| 6 | >5 pages rejected: `SourcePreparationError` names count+limit; use case returns `SourceRejected` without extract/persist; Telegram replies with page count + 5-page limit + "not be satisfied"; CLI prints reason and exits 1; no page silently dropped | `test_source_preparation.py::test_pdf_six_pages_rejected_naming_count_and_limit` ("6" and "5" in message); `tests/application/test_expense_recording.py::test_preparation_error_returns_source_rejected[ONE_SHOT]` / `[CONVERSATIONAL]` (`extract`/`refine`/`save` not called, no store state); `test_telegram_bot.py::TestPdfHandler::test_source_rejected_replies_with_explicit_rejection` (reply has "8 pages", "5 pages", "not be satisfied"); `test_cli_extraction.py::test_pdf_rejection_prints_reason_and_exits_one` (`SystemExit` code 1, reason on stdout) |
| 7 | Invalid/corrupt bytes and 0-page PDF rejected via same `SourcePreparationError` → `SourceRejected` path with understandable message | `test_source_preparation.py::test_invalid_pdf_bytes_rejected`; `test_pdf_zero_pages_rejected` (mocked 0-page PDFium document — a valid 0-page PDF cannot be produced by Pillow); use-case mapping covered by `test_preparation_error_returns_source_rejected` (parametrized over both modes) |
| 8 | Incomplete PDF extraction: CONVERSATIONAL → `CorrectionOpened` + pending state + existing missing-fields prompt; ONE_SHOT → `ExtractionIncomplete`, nothing persisted | `tests/application/test_expense_recording.py::test_pdf_incomplete_conversational_opens_correction` (store has pending, `refine` not called) and `test_pdf_incomplete_one_shot_returns_incomplete` (no save, no state); `test_telegram_bot.py::TestPdfHandler::test_partial_extraction_asks_for_missing` (byte-identical missing-fields prompt) |
| 9 | `FreeTextSourceView` extraction and `refine()` byte-for-byte unchanged (dSPy CoT path untouched except entry signature) | `tests/adapters/out/test_dspy_extraction.py::TestExtractText::test_extract_text_returns_extraction_result`, `TestValidation` (all 8 tests), `TestRefine` (all 5 tests), `TestRetry` (both); `tests/adapters/out/test_dspy_extraction_logging.py` (all 8 tests) |
| 10 | No framework/IO import in `domain/` | `tests/domain/test_source_types.py` (5 tests); `grep -rn "^import\|^from" src/expense_report/domain/` shows `source_types.py` imports only `from enum import Enum` |
| 11 | `SourceView` never carries base64/OpenAI parts/PDFium objects/resize-model metadata | `tests/ports/test_source_preparation.py::TestFreeTextSourceView`, `TestReceiptPagesSourceView`, `TestSourceViewUnion` (frozen dataclasses holding `str` / `tuple[bytes, ...]` only) |
| 12 | Inbound adapters never render/resize, no pypdfium2/PIL on the recording path | `grep -rn "pypdfium2\|PIL\|render\|resize" src/expense_report/adapters/inbound/` → no matches; Telegram/CLI translate input to `RecordExpense` only (tests 1, 3, 6, 8 above) |
| 13 | Extraction adapter does not count PDF pages / enforce cap / branch on `SourceType` | `grep -n "page_count\|MAX_PDF\|SourceType" src/expense_report/adapters/out/dspy_extraction.py` → no matches; `test_dspy_extraction.py` multi-page test proves branching on `SourceView` only |
| 14 | No new driving port, no new use case, exactly one `SourcePreparationPort` | `tests/ports/test_source_preparation.py::TestSourcePreparationPortProtocol`; `tests/application/test_expense_recording.py::test_use_case_satisfies_expense_recording_port` (reused use case); `tests/adapters/out/test_source_preparation.py::TestPortCompliance::test_adapter_satisfies_source_preparation_port` |
| 15 | Correction routing stays text-only; image/PDF never enter `refine()` on fresh flow | `test_expense_recording.py::test_correction_resolve_saves_clears_and_returns_resolved`, `test_correction_still_incomplete_increments_attempt`, `test_correction_maxed_out_returns_limit_reached_without_refining` (each asserts `preparation.prepare.assert_not_called()`); `test_pdf_incomplete_conversational_opens_correction` asserts `extraction.refine.assert_not_called()` |
| 16 | No page of an accepted PDF dropped or reordered | `test_source_preparation.py::TestPdfPreparation::test_pdf_preserves_page_order` (4 distinct-color Pillow pages; each rendered JPEG's pixel matches the source page's color in order) |
| 17 | No changes to repository/query logic, keyboards, callback data, existing photo/text texts; no `.feature` changes | `git diff --stat` shows no `repository.py` / `expense_queries.py` changes; behave runs the unchanged 7 feature files (27 scenarios, 217 steps pass); photo/text message texts asserted byte-identical (tests 4 and 8) |

### Red-State Evidence (before implementation)

**Red A — new contract pieces (before `domain/source_types.py`, `ports/source_preparation.py`, `adapters/out/source_preparation.py` existed):**

```text
$ uv run pytest tests/domain/test_source_types.py tests/ports/test_source_preparation.py tests/adapters/out/test_source_preparation.py -q
ImportError while importing test module '.../tests/ports/test_source_preparation.py'.
E   ModuleNotFoundError: No module named 'expense_report.domain.source_types'
ERROR tests/domain/test_source_types.py
ERROR tests/ports/test_source_preparation.py
ERROR tests/adapters/out/test_source_preparation.py
!!!!!!!!!!!!!!!!!!! Interrupted: 3 errors during collection !!!!!!!!!!!!!!!!!!!!
3 errors in 0.09s
```

**Red B — contract migration (tests updated to the new contract against the old implementation):**

```text
$ uv run pytest -q
64 failed, 204 passed in 1.59s
```

Failure categories (all expected): `TypeError: __init__() takes 4 positional arguments but 5 were given`
for the use-case constructor, missing `source_type` argument on `extract`, missing `_make_pdf_handler`
(`ImportError`), missing `extract-from-pdf` subcommand (`SystemExit: 2` from argparse), and assertion
differences on the old `Literal`-based `RecordExpense` shapes.

### Full Verification Chain (final)

```text
$ uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
109 files left unchanged
All checks passed!
All checks passed!
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/clt/PersonalProjects/expese-report-bot
configfile: pyproject.toml
testpaths: tests
plugins: typeguard-4.4.3, anyio-4.14.2
collected 268 items

tests/adapters/inbound/test_authorization.py ....................        [  7%]
tests/adapters/inbound/test_cli_extraction.py ..............             [ 12%]
tests/adapters/inbound/test_logging_config.py .....                      [ 14%]
tests/adapters/inbound/test_telegram_bot.py ............................ [ 25%]
..........................                                               [ 34%]
tests/adapters/inbound/test_telegram_bot_logging.py ............         [ 39%]
tests/adapters/out/test_dspy_extraction.py ..........................    [ 48%]
tests/adapters/out/test_dspy_extraction_logging.py ........              [ 51%]
tests/adapters/out/test_source_preparation.py ..............             [ 57%]
tests/adapters/out/test_sqlite_repository.py ..........................  [ 66%]
tests/adapters/out/test_sqlite_repository_logging.py ......              [ 69%]
tests/application/test_correction_state.py ......                        [ 71%]
tests/application/test_expense_queries.py .............                  [ 76%]
tests/application/test_expense_recording.py ........................     [ 85%]
tests/domain/test_correction_state.py ......                             [ 87%]
tests/domain/test_csv_generator.py ......                                [ 89%]
tests/domain/test_models.py ..........                                   [ 93%]
tests/domain/test_source_types.py .....                                  [ 95%]
tests/ports/test_extraction.py ..                                        [ 95%]
tests/ports/test_repository.py ..                                        [ 96%]
tests/ports/test_source_preparation.py .........                         [100%]

============================= 268 passed in 10.76s =============================

7 features passed, 0 failed, 0 skipped
27 scenarios passed, 0 failed, 0 skipped
217 steps passed, 0 failed, 0 skipped
Took 0min 0.399s
```
