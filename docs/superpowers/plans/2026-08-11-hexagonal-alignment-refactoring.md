# Hexagonal Alignment Refactoring — Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan phase-by-phase. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the codebase into full alignment with the hexagonal architecture (ADR 0001, clarified by ADR 0006) by resolving the remaining items in `docs/architecture/hexagonal-alignment-todo.md`: ARCH-001 (photo + correction slices), ARCH-002, ARCH-003, ARCH-004, ARCH-005, ARCH-006 — one feature at a time, each landing as dedicated commits on a dedicated worktree, with the whole suite green at the end of every phase.

**Architecture:** Per the approved design `docs/superpowers/specs/2026-07-21-expense-recording-architecture-design.md` and the tracker. Driving Adapters (Telegram, CLI) translate transport and render; the application layer owns workflow decisions behind driving Ports; driven Adapters implement driven Ports. No speculative Seams: a new Port requires concrete variation.

**Tech Stack:** Python 3.12+, frozen dataclasses, `Enum`, `Protocol`, pytest, behave, `unittest.mock`, Ruff, ty, uv.

## Current State (verified 2026-08-11)

Baseline on `main` (`0d30ff3`): **189 pytest passed, 27 behave scenarios passed**, ruff + ty clean.

| ARCH item | Priority | Status | Remaining work |
|-----------|----------|--------|----------------|
| ARCH-001 | P0 | In progress | Free-text tracer merged (PR #5). **Remaining:** (a) Telegram photo path still calls `ExtractionPort.extract()` directly and constructs/saves `Expense` inside `_respond_to_extraction`; CLI `extract-from-image` duplicates the legacy extract→save pipeline; (b) Correction lifecycle (`_handle_correction`: max-out check, refine, save, clear, attempt counting) still lives in PTB handlers. |
| ARCH-002 | P0 | In progress | ADR 0006 accepted; ADR 0001 consequences already reference it. **Remaining:** closes together with ARCH-001 — all recording paths must exercise the driving Interface; tracker status + decision log. |
| ARCH-003 | P1 | Not started | `/list` (period discovery, currency aggregation), `/report` (month selection + CSV), `/delete` (command + callback) policy entirely inside `telegram_bot.py`. |
| ARCH-004 | P1/P2 | Not started | Config knowledge distributed: `main.py` reads env, authorization reads own env, `DspyExtractionAdapter` reads `LLM_*` env in `__init__` **and again** in `_call_image_with_retry`; CLI constructs concrete adapters separately. |
| ARCH-005 | P2 | Not started | Conditional placement decisions: `CorrectionStore` (resolves with ARCH-001 correction slice), `generate_csv` (resolves with ARCH-003 report slice). |
| ARCH-006 | P2 | Not started | ADR 0002 says every extraction goes through dSPy; image path bypasses it via direct OpenAI client. Dead code: `ExpenseImageSignature`, `_image_extractor`, `_DATE_RE`. |

## Global Constraints

- Follow `AGENTS.md`, `CONTEXT.md`, all ADRs, and the tracker document.
- **Worktree isolation:** ALL refactoring work happens in the dedicated worktree `.worktrees/hexagonal-alignment` on branch `refactor/hexagonal-alignment`. Never commit refactoring changes to `main` directly.
- **TDD red-first:** never write implementation before a failing test. Commit the failing tests as a dedicated `test:` commit, then the implementation as a dedicated `refactor:` commit.
- **EDD:** write expectations in `docs/expectations/<feature>.md` before implementation of each phase; prove each expectation with executed evidence at phase end.
- **Verification chain** after EVERY file-changing task (paste actual output as evidence):
  ```bash
  uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
  ```
  (If `uvx` fails with a read-only tool dir, prefix `UV_TOOL_DIR=/tmp/uv-tools UV_CACHE_DIR=/tmp/uv-cache`.)
- **Commit discipline:** one dedicated commit per completed bit — expectations (`docs:`), failing tests (`test:`), implementation (`refactor:`), ADR/tracker updates (`docs:`). Commit through the installed gitleaks pre-commit hook; never `--no-verify`.
- No new dependencies. No changes to driven port Interfaces (`ExtractionPort`, `ExpenseRepositoryPort`) unless a phase explicitly calls for it.
- Preserve all user-visible behavior (Telegram messages, keyboards, CLI output) exactly, unless a phase's expectations document states otherwise.
- Pre-commit hooks are already installed (`.git/hooks/pre-commit`, shared with worktrees).
- Execute phases in order; do not start a phase while the previous one is red.
- After completing each ARCH item: set its tracker status, append a decision-log entry in `docs/architecture/hexagonal-alignment-todo.md` section 8, and update section 6.

## Execution Model

Per `AGENTS.md`, the main agent orchestrates: for each phase, capture context in a handoff, formulate a self-contained worker brief (acceptance criteria, hexagonal boundaries, EDD expectations, exact verification command), delegate implementation in spawn mode, then review the returned evidence (optionally with a `reviewer` subagent) before accepting.

---

## Phase 0 — Worktree Setup & Baseline

**Files:**
- Create: `.worktrees/hexagonal-alignment/` (git worktree)
- Create: `docs/superpowers/plans/2026-08-11-hexagonal-alignment-refactoring.md` (this document)

- [ ] **Step 1: Create the dedicated worktree and branch**

```bash
cd /home/clt/Projects/expense-report-bot
git worktree add .worktrees/hexagonal-alignment -b refactor/hexagonal-alignment main
cd .worktrees/hexagonal-alignment
uv sync
```

- [ ] **Step 2: Verify the baseline is green in the worktree**

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
```

Expected: 189 pytest passed, 27 behave scenarios passed, ruff/ty clean.

- [ ] **Step 3: Commit this plan as the branch's first commit**

```bash
git add docs/superpowers/plans/2026-08-11-hexagonal-alignment-refactoring.md
git commit -m "docs: plan hexagonal alignment refactoring"
```

---

## Phase 1 — ARCH-001 (photo slice): Receipt-photo Recording behind the driving Port

**Goal:** Telegram photo path and CLI `extract-from-image` both route through `ExpenseRecordingPort.record()` with `source_type="image"`; neither adapter constructs or saves an `Expense` anymore. The use case already handles any `source_type`; this slice deletes the duplicated legacy pipelines.

**Files:**
- Create: `docs/expectations/expense-recording-photo-slice.md`
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py` (`_make_photo_handler`, delete `_respond_to_extraction`'s expense construction)
- Modify: `src/expense_report/adapters/inbound/cli_extraction.py` (`extract-from-image` path)
- Modify: `tests/application/test_expense_recording.py` (image recording through the port)
- Modify: `tests/adapters/inbound/test_telegram_bot.py`, `tests/adapters/inbound/test_cli_extraction.py` (thin-adapter translation tests)

**Key expectations to capture (EDD doc, Step 1):**
1. Complete receipt photo → `RecordExpense(user_id, source=image_bytes, source_type="image", mode=CONVERSATIONAL, receipt_photo_id=<telegram file_id>)` → `ExpenseRecorded`; saved expense keeps the Telegram `file_id` as `receipt_photo_id`.
2. Incomplete receipt photo → `ExtractionIncomplete`; nothing persisted; Telegram opens pending correction exactly as today.
3. CLI `extract-from-image` → `RecordExpense(..., source_type="image", mode=ONE_SHOT, receipt_photo_id=None)`; prints existing output; incomplete → not saved.
4. Must NOT happen: adapters construct `Expense` or call `repository.save` on the photo path; `_respond_to_extraction` orchestration survives; Telegram download/rendering changes.

- [ ] **Step 1: Write EDD expectations** → commit `docs: capture photo recording slice expectations`
- [ ] **Step 2: Red — application workflow tests**: complete image records expense with `receipt_photo_id` preserved; incomplete image returns `ExtractionIncomplete` without persisting; extraction exceptions propagate. Plus thin-adapter tests proving Telegram/CLI only translate and render. Run chain, show failures. → commit `test: cover photo recording through driving port`
- [ ] **Step 3: Green — implementation**: route `_make_photo_handler` through `ExpenseRecordingPort`; delete `_respond_to_extraction`'s orchestration (keep/rename only the incomplete-reply helper); route CLI image path through `ExpenseRecordingUseCase`; drop now-unused imports (`Expense`, `datetime`, `ExtractionPort` where unused). Run full chain. → commit `refactor: route receipt photo recording through driving port`
- [ ] **Step 4: Behave regression** (`telegram_bot.feature`, `cli_extraction.feature`) green; map expectations → evidence in the EDD doc. → commit `docs: record photo slice evidence`

---

## Phase 2 — ARCH-001 (correction slice): Correction Lifecycle behind the driving Port

**Goal:** The application layer owns the Correction lifecycle: pending-state routing, `refine()` vs `extract()` choice, attempt counting, max-out, save-and-clear. Telegram handlers become pure translation + rendering. Includes the ARCH-005 `CorrectionStore` ownership decision.

**Design step required (before EDD):** outcome shapes for the correction conversation. Starting point from the approved spec (section "Outcomes"): extend the union with correction-specific outcomes, e.g. `CorrectionOpened`, `CorrectionResolved`, `CorrectionStillIncomplete(attempt_count, missing_fields)`, `CorrectionLimitReached`. Decide whether `record()` stays the single operation (use case routes on pending state — the spec's chosen "mode-aware single operation" alternative) — document the chosen shape in the expectations doc; add an ADR only if the shape contradicts ADR 0006.

**Files:**
- Create: `docs/expectations/correction-lifecycle.md`
- Modify: `src/expense_report/ports/expense_recording.py` (outcome union extension)
- Modify: `src/expense_report/application/expense_recording.py` (correction orchestration; depends on `CorrectionStore` internally — NO new port, per spec)
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py` (delete `_handle_correction` orchestration; slim `_make_text_handler`)
- Move: `CorrectionStore` from `domain/correction_state.py` → `application/` (workflow-owned session state); `PendingCorrection` entity stays in domain
- Modify: `tests/application/test_expense_recording.py` (PTB-free correction permutations), `tests/adapters/inbound/test_telegram_bot.py` (thin correction rendering tests)

**Key expectations:**
1. Text from a user WITH pending correction → use case calls `refine()` (never `extract()`), and on complete result saves expense, clears state, returns `CorrectionResolved` (attempt semantics: `attempt_count` starts at 1, max 3 — `maxed_out` invariant preserved).
2. Refined-but-incomplete → attempt increments, state updated, returns still-incomplete outcome carrying attempt count and missing fields.
3. Text from a user whose correction is maxed out → state cleared, limit-reached outcome, NO refine call, nothing persisted.
4. Text from a user with NO pending correction → normal extract path (regression).
5. Must NOT happen: PTB types in the use case; `CorrectionStore` access from the Telegram adapter; behavior change in rendered messages.

- [ ] **Step 1: Design + EDD expectations** → commit `docs: capture correction lifecycle expectations`
- [ ] **Step 2: Red — workflow tests** for all correction permutations without PTB types. → commit `test: cover correction lifecycle through driving port`
- [ ] **Step 3: Green — implement correction orchestration in the use case; slim the Telegram adapter.** → commit `refactor: own correction lifecycle in application layer`
- [ ] **Step 4: Move `CorrectionStore` to `application/`** (tests stay green; mechanical move). → commit `refactor: colocate correction state with owning workflow`
- [ ] **Step 5: Behave regression** (`correction.feature` etc.) green; evidence mapping. → commit `docs: record correction slice evidence`

---

## Phase 3 — Close ARCH-001 & ARCH-002

- [ ] **Step 1: Verify tracker completion criteria for ARCH-001/002**: Telegram + CLI share one recording implementation (photo AND text AND correction); workflow tests exercise the same driving Interface without PTB/argparse; ADR 0001 wording matches reality (ADR 0006 supersedes the "every adapter implements a port" clause — already reflected in ADR 0001 consequences; amend only if drifted).
- [ ] **Step 2: Update tracker**: statuses `Resolved`, decision-log entries, section 6 update. → commit `docs: resolve ARCH-001 and ARCH-002 in alignment tracker`

---

## Phase 4 — ARCH-003: Browsing / Reporting / Deletion Policy (three sub-phases)

**Design step required (grilling session before 4a):** module/port shape for query-side use cases. Decision points: one `ExpenseQueryPort` vs purpose-named ports per capability (browse / report / delete); what policy types are needed (period selection, currency aggregation, keyboard-independent month/year views); CSV ownership (ARCH-005): `generate_csv` moves out of `domain/` into the reporting policy module unless grilling concludes otherwise. Record outcome in the expectations doc; ADR only if load-bearing.

Each sub-phase follows the same TDD/EDD/commit rhythm: expectations (`docs:`) → red policy tests without PTB (`test:`) → implementation + slimmed adapter (`refactor:`) → behave regression + evidence (`docs:`).

### 4a — `/list` browsing policy
- Application owns: year/month discovery (`get_months_with_expenses` over current + previous year), active-period selection (current month if data, else most recent with data), month/year view retrieval, per-currency aggregation.
- Telegram keeps: callback-string decoding (`year:n` / `month:y:m`), keyboards, message text rendering.
- Tests: period selection permutations (no expenses at all, only previous year, current year partial), multi-currency totals — all PTB-free.

### 4b — `/report` policy (+ CSV placement)
- Application owns: current-month selection, empty-month outcome, report generation (CSV serialization moved here from `domain/` per ARCH-005 decision).
- Telegram keeps: `BytesIO`, filename, document delivery.
- Tests: report content policy without PTB; empty-month path.

### 4c — `/delete` policy
- Application owns: delete-by-id scoped to user, found/not-found outcomes.
- Telegram keeps: command parsing (`/delete <id>` validation messages), callback decoding, strikethrough rendering.
- Tests: deletion outcomes without PTB.

Commits per sub-phase: 4 (docs/test/refactor/docs) = 12 total. Then:

- [ ] **Final step: tracker update** — ARCH-003 `Resolved` + decision log. → commit `docs: resolve ARCH-003 in alignment tracker`

---

## Phase 5 — ARCH-004: Composition / Configuration Consolidation

**Goal:** each executable validates configuration once at its entry point; driven adapters receive explicit configuration; the repeated `LLM_*` env reads in `DspyExtractionAdapter._call_image_with_retry` are removed. Must preserve ADR 0004 (logging configured at entry point).

**Files:**
- Create: `docs/expectations/configuration-composition.md`
- Create: config parsing module (shape decided in the phase's design step — e.g. a frozen `LlmSettings`/`BotConfig` parsed by a small `config` module per entry point)
- Modify: `src/expense_report/adapters/out/dspy_extraction.py` (constructor takes explicit settings, no env reads)
- Modify: `src/expense_report/adapters/inbound/main.py`, `cli_extraction.py`, `authorization.py` (explicit values in, no hidden env reads)
- Modify: extraction/CLI/startup tests (no more process-wide env patching for adapter construction)

**Key expectations:**
1. Missing required value (`TELEGRAM_BOT_TOKEN`, `LLM_*`) → clear startup failure naming the missing variable; defaults (`EXPENSE_DB_PATH`, `LOG_LEVEL`, unauthorized-log path) unchanged.
2. `DspyExtractionAdapter` never reads `os.environ` — image and text paths use constructor-provided settings.
3. Must NOT happen: behavior change for valid configurations; logging still configured first (ADR 0004).

Commits: expectations (`docs:`) → red config tests (`test:`) → explicit-settings refactor (`refactor:`) → evidence + tracker `Resolved` (`docs:`).

---

## Phase 6 — ARCH-006: ADR 0002 Reconciliation + Dead-code Removal

**Goal:** ADR matches reality. Recommended direction (confirm in the phase): the direct image path is an intentional, documented exception (context-window constraint); amend ADR 0002 accordingly; delete `ExpenseImageSignature`, `self._image_extractor`, and `_DATE_RE`. (The alternative — consolidate everything on direct calls and drop dSPy — is a separate, larger decision and is OUT of scope here.)

- [ ] **Step 1: Amend ADR 0002** (status: amended by ADR 0007) → commit `docs: reconcile ADR 0002 with direct image extraction path`
- [ ] **Step 2: Remove dead code**; adjust tests coupled to constructor internals; full chain green. → commit `refactor: remove unused dspy image extraction machinery`
- [ ] **Step 3: Tracker** — ARCH-006 `Resolved` + decision log. → fold into step 1 commit or separate `docs:` commit.

---

## Phase 7 — ARCH-005 Closure & Final Tracker Update

- [ ] **Step 1: Record final placement rationale** for `CorrectionStore` (application-owned session state, single in-memory implementation, no speculative port — per ADR 0006 consequences) and `generate_csv` (moved in Phase 4b, or retained with rationale). New ADR only if load-bearing for future reviews. → commit `docs: record ARCH-005 placement decisions`
- [ ] **Step 2: Final tracker sweep** — all items resolved/deferred, decision log complete, execution-order section updated. → commit `docs: finalize hexagonal alignment tracker`
- [ ] **Step 3: Final full verification** in the worktree: `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave` — paste complete output.

---

## Phase 8 — Merge

- [ ] **Step 1: Push branch and open PR** `refactor/hexagonal-alignment` → `main` (or merge locally, per user choice made at kickoff).
- [ ] **Step 2: After merge, clean up**: `git worktree remove .worktrees/hexagonal-alignment`, delete merged branch, prune the stale `/tmp/erb-base-review` worktree entry (`git worktree prune`).

## Commit Map (summary)

| Phase | Commits |
|-------|---------|
| 0 | 1 (plan) |
| 1 photo slice | 4 (docs, test, refactor, docs) |
| 2 correction slice | 5 (docs, test, refactor, refactor, docs) |
| 3 close P0 | 1 (docs) |
| 4 ARCH-003 | 3 × 4 + 1 = 13 |
| 5 ARCH-004 | 4 |
| 6 ARCH-006 | 3 |
| 7 closure | 2 |

Every commit lands only after its verification chain passes; every phase ends green.

## Open Decisions for Kickoff

1. **Merge strategy:** one PR at the end vs. per-phase PRs from sub-branches (worktree switches branches). Default in this plan: single long-lived branch, one PR at the end.
2. **ARCH-004 priority:** run it as Phase 5 (after ARCH-003) per the tracker's default, or interleave earlier — it is independent.
3. **ARCH-006 direction:** confirm "documented exception + dead-code removal" vs. scheduling the larger dSPy-consolidation discussion.
