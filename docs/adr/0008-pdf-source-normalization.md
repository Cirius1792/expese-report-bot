# ADR 0008: PDF Source Normalization

**Date:** 2026-08-21
**Status:** Accepted

## Context

The bot accepts receipt **photos** and free-text expense descriptions. Users now
want to send receipt **PDFs** (1–5 pages; multi-page = one long invoice). PDFs
with more than 5 pages must be **rejected** with an explicit user-facing message
— silent truncation of an invoice risks wrong amounts (user decision, 2026-08-21).

Raw `bytes` currently leak through both driving and driven ports: the driving
adapters pass raw upload bytes straight into `ExtractionPort.extract`, and the
extraction adapter interprets them (image vs text) itself. Adding PDFs would
force the extraction adapter to also count pages and enforce limits, and would
leave the application use case blind to a real workflow step (source
normalization) that happens before extraction.

## Decision

Introduce source normalization as a separate driven capability (Option B):

- **New driven port** `SourcePreparationPort` (`ports/source_preparation.py`):
  `prepare(source: str | bytes, source_type: SourceType) -> SourceView`.
  `SourceView = FreeTextSourceView(text) | ReceiptPagesSourceView(page_images)` —
  a ports-boundary DTO, not a domain entity. It never carries base64, LLM chat
  parts, PDFium objects, or resize/model metadata.
- **`SourceType` enum** (`domain/source_types.py`): TEXT / IMAGE / PDF, replacing
  the `Literal["image", "text"]` in `RecordExpense` and `ExtractionPort.extract`.
- **Same use case, one more dependency:**
  `ExpenseRecordingUseCase(preparation, extraction, repository, correction_store)`.
  Fresh path = `view = preparation.prepare(...)` then `extraction.extract(view)`.
  New outcome `SourceRejected(reason)` in `ports/expense_recording.py`;
  `SourcePreparationError` (defined in the preparation port) is caught in the
  use case and mapped to it. Correction routing stays text-only and unchanged.
- **Strategy dispatch lives in the adapter**
  `adapters/out/source_preparation.py` (`SourcePreparationAdapter`, a `match`
  on `SourceType`): TEXT → free-text view; IMAGE → one-page view (raw bytes, no
  decode); PDF → pypdfium2 renders pages (scale 2, JPEG quality 92) in order;
  >5 pages / 0 pages / invalid bytes → `SourcePreparationError` naming the page
  count and the 5-page limit.
- **Extraction port narrows:** `extract(source: SourceView)`. The dSPy adapter
  branches on the view: free text → existing ChainOfThought path (unchanged);
  receipt pages → **one** vision request with 1..N image parts (1536px resize +
  base64 stay in this adapter — model-facing, not normalization).
- **Inbound stays a pure interface layer:** Telegram gains a
  `filters.Document.PDF` handler (download → `SourceType.PDF`, CONVERSATIONAL,
  `receipt_photo_id=None`); `SourceRejected` renders an explicit rejection
  (page count + 5-page limit). CLI gains `extract-from-pdf` (ONE_SHOT;
  rejection → print reason, exit code 1). `WELCOME_MESSAGE` mentions PDFs.
- **Dependency:** `pypdfium2` added via `uv add` (pure wheel, Apache-2.0, no
  system poppler → Dockerfile untouched).

## Considered Options

| Option | Notes |
|--------|-------|
| **B — `SourcePreparationPort` + `SourceView` (chosen)** | Use case owns the prepare→extract shape (consistent with ADR 0006, application-owned orchestration); extraction contract narrows to semantic input; rejection is a first-class outcome |
| A — strategy inside the extraction adapter | Keeps raw `bytes` leaking through both driving and driven ports; leaves the use case blind to a workflow step; forces the extraction adapter to count pages and enforce the cap |
| C — per-type preparation ports | "Prepare a receipt source" is one capability; per-type ports model implementation detail as port surface |

## Consequences

- The use case explicitly orchestrates `prepare()` → `extract()` and can reject
  a source before any LLM call or persistence.
- `SourceView` at the ports boundary keeps the domain free of LLM/plumbing
  fields; `domain/source_types.py` is a plain enum with zero framework/IO.
- The extraction adapter never counts PDF pages, never enforces the 5-page cap,
  and never branches on `SourceType` — it only consumes a `SourceView`.
- Inbound adapters remain pure translators of Telegram/CLI input into
  `RecordExpense`; they never render or resize.
- One PDF = exactly one expense; >5 pages is rejected fail-fast with an explicit
  user-facing message (no silent truncation).
- Test PDF fixtures are generated in-memory with Pillow (already a dependency);
  no binary fixtures, no new dev dependencies.
