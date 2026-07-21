# Hexagonal Architecture Alignment — Status & Tracker

## 1. Purpose

Track and prioritise architectural deepening opportunities in the Expense Report Bot codebase against the hexagonal (ports & adapters) pattern chosen in ADR 0001. This is a **findings-and-decisions document**, not an implementation plan. Each item is self-contained for one-issue-at-a-time execution.

### Scope

- Source under `src/expense_report/` (domain, ports, adapters/inbound, adapters/out).
- Test structure relevance where it illuminates a Seam or Interface gap.
- ADR decisions that constrain or conflict with each finding.

### Non-Goals

- Proposing concrete Python Protocol definitions for new Interfaces — that is design work for the execution of each item.
- Modifying ADRs, source code, tests, expectations, or any other repository file.
- Re-litigating accepted ADRs unless friction is concrete enough to warrant reopening (marked clearly).
- Prescribing a DI framework, container library, or package path choice.

---

## 2. Current Verdict on Hexagonal Alignment

**Partially aligned. Driven (outbound) side is broadly correct; driving (inbound) side has no Application/Use-Case Module and no driving-side Port Protocols.**

| Layer | Alignment | Key Evidence |
|-------|-----------|--------------|
| `domain/` | **Broadly aligned** (with debatable items) | Entities (`Expense`, `ExtractionResult`, `PendingCorrection`) are framework-independent domain dataclasses. `generate_csv` has no external side effects, but CSV is an output-format policy — placement is debatable (see ARCH-005). |
| `ports/` | **Partial** | Two driven-side Protocols (`ExtractionPort`, `ExpenseRepositoryPort`) exist. Each has one production Adapter, so each Seam remains hypothetical. No driving-side use-case Interface exists. ADR 0001's "every adapter must implement a port protocol" correctly describes driven Adapters but not driving Adapters, which consume driving ports. |
| `adapters/out/` | **Broadly aligned** | `DspyExtractionAdapter` implements `ExtractionPort`. `SqliteExpenseRepository` implements `ExpenseRepositoryPort`. Both depend inward on core types. The extraction Implementation nevertheless conflicts with ADR 0002 (see ARCH-006). |
| `adapters/inbound/` | **Needs work** | `telegram_bot.py` contains business orchestration for Correction, Expense recording, browsing, and reporting inside PTB handler factories. No application/use-case Module owns these workflows. `cli_extraction.py` duplicates the extract→check→save flow (see ARCH-001). |
| Composition (`main.py`) | **Partial** | `main.py` is a composition root for Telegram, but environment parsing and construction knowledge are distributed across `main.py`, authorization, the extraction Adapter, and the CLI entry point (see ARCH-004). |

---

## 3. Best-Practice Baseline

### Authoritative Sources

| Source | Principle | Relevance |
|--------|-----------|-----------|
| **Cockburn 2005** — [Hexagonal Architecture (original article)](https://alistair.cockburn.us/hexagonal-architecture) | "Create your application to work without either a UI or a database so you can run automated regression-tests against the application… The application communicates over **ports** to external agencies." | The core application logic (use cases) must be testable through a port without any adapter attached. |
| **Cockburn 2005** — same source | "A **port** identifies a purposeful conversation. There will typically be multiple **adapters** for any one port." | Ports are named for application purpose rather than transport technology. The review principle applied here is: one Adapter means a hypothetical Seam; two Adapters mean a real Seam. |
| **Cockburn 2005** — same source | "The rule to obey is that code pertaining to the inside part should not leak into the outside part." | Framework and storage concerns should not leak into core Modules. |
| **Fowler 2004** — [Inversion of Control Containers and the Dependency Injection pattern](https://martinfowler.com/articles/injection.html) | "Separating configuration from use… a separate assembler module [injects] the implementation into the [consumer]." | Composition is separated from Modules that use the selected Adapters. |
| **Fowler 2004** — same source | "The choice between [DI and Service Locator] is less important than the principle of **separating configuration from use**." | The principle is authoritative; the mechanism is a project choice. |
| **Thoughtworks** — [Hexagonal architecture explained through a practical example](https://www.thoughtworks.com/en-in/insights/blog/architecture/hexagonal-architecture-explained-practical-example) | The application layer coordinates workflows while domain Modules hold business rules. | Workflow orchestration should not be embedded in a driving Adapter. |
| **Hexagonal practice represented by the sources above** | Driving ports are use-case Interfaces that driving Adapters call; driven ports are Interfaces that driven Adapters implement. | ADR 0001's "every adapter implements a port protocol" only describes the driven side. |

### Distinction: Strong Guidance vs Optional Convention

| Category | Item | Why |
|----------|------|-----|
| **Strong** | Business logic must not leak into adapters | Cockburn's core motivation — testability, swappability. |
| **Strong** | A composition root must exist where adapters are wired to ports | Fowler: separating config from use is the fundamental principle. |
| **Strong** | Core Modules must not depend on frameworks or external effects | Cockburn's inside/outside asymmetry. |
| **Review principle** | One Adapter = hypothetical Seam; two Adapters = real Seam | Do not introduce a new Seam solely for imagined variation. |
| **Optional** | `adapters/in/` vs `adapters/inbound/` naming | Cosmetic; ADR 0003 chose `inbound` for Python 3.10 compatibility. |
| **Optional** | Whether driving Adapters must also implement a Protocol | ADR 0001's wording implies this, but Cockburn's actual pattern says driving Adapters **call into** ports, not implement them. Revisit ADR 0001 if a driving Protocol is added. |

---

## 4. Correctly Aligned Areas

| Module | Status | Why |
|--------|--------|------|
| `domain/models.py` | ✅ Aligned | `Expense` (frozen dataclass), `ExtractionResult` (frozen dataclass with `is_complete` property). Zero framework/IO imports. Pure domain data. |
| `domain/correction_state.py` (entity) | ✅ Aligned | `PendingCorrection` (mutable `@dataclass` with `maxed_out` invariant) — pure domain entity. `CorrectionStore` placement is debatable — see ARCH-005. |
| `domain/csv_generator.py` | ⚠️ Debatable | Pure function `generate_csv(expenses: list[Expense]) -> str` uses only stdlib `csv.StringIO` with zero external side effects, so it *can* live in domain. However, CSV is an output-format serialization policy, not domain logic — placement should be revisited when browse/report design clarifies (see ARCH-005). |
| `ports/extraction.py` | ✅ Aligned | `ExtractionPort` Protocol with `extract()` and `refine()` — narrow, complete Interface for the extraction conversation. Single production Adapter (`DspyExtractionAdapter`) — hypothetical Seam. |
| `ports/repository.py` | ✅ Aligned | `ExpenseRepositoryPort` Protocol. Single production Adapter (`SqliteExpenseRepository`). Tests use `:memory:` SQLite (same Adapter class, different configuration) — not a second Adapter. Hypothetical Seam only. |
| `adapters/out/dspy_extraction.py` | ✅ Aligned | `DspyExtractionAdapter` implements `ExtractionPort`. Satisfies Dependency Inversion: depends on `ports/` and `domain/`, not the reverse. |
| `adapters/out/sqlite_repository.py` | ✅ Aligned | `SqliteExpenseRepository` implements `ExpenseRepositoryPort`. Same direction. |
| `adapters/inbound/authorization.py` | ✅ Aligned (as a PTB concern) | ADR 0005 intentionally centralises Telegram auth in a `TypeHandler` guard. Correct for PTB's handler model and does not leak into domain. |

---

## 5. Prioritised Checklist

### Status Legend

| Status | Meaning |
|--------|---------|
| `Not started` | Not yet addressed. |
| `In progress` | Being worked in current iteration. |
| `Resolved` | Fix merged to `main`. |
| `Deferred` | Deliberately postponed; ADR or decision log entry exists. |
| `Wontfix` | Closed as not worth pursuing; ADR or decision log entry exists. |

### Updating the Document

After completing an item:
1. Change its status to `Resolved`, `Deferred`, or `Wontfix`.
2. Append a decision log entry (section 8) with date, item ID, summary of what was done, and any ADR created.
3. If the resolution creates a new ADR, update ADR links accordingly.

---

### ARCH-001: Expense Recording and Correction Orchestration

| Field | Value |
|-------|-------|
| **Priority** | P0 — blocks all other driving-side improvements |
| **Status** | `Not started` |
| **Files/Symbols** | `src/expense_report/adapters/inbound/telegram_bot.py`: `_make_photo_handler`, `_make_text_handler`, `_respond_to_extraction`, `_handle_correction`; `src/expense_report/adapters/inbound/cli_extraction.py`: `main()` |
| **Problem** | Business orchestration (decide if extraction is complete → if so, create Expense domain object → save to repository → format response; if not, set up Correction → re-extract → save → clear) lives **inside** PTB handler factories. There is no Application/Use-Case Module that represents "record an expense from an extraction" or "handle a correction attempt." The Telegram Adapter's `register_handlers` takes concrete dependencies (`ExtractionPort`, `ExpenseRepositoryPort`, `CorrectionStore`) but the orchestration decision tree, expense creation, and response formatting are embedded inside handler closures. The CLI adapter's `main()` independently re-implements its own `extract→check→save` pipeline — the same logic in a second location, with no correction flow at all. Two copies of the same pipeline means bugs can exist in one but not the other. |
| **Deletion test** | Delete `telegram_bot.py`. The CLI adapter still exists but handles only extract→save with no correction flow. Delete `cli_extraction.py`. CLI users lose the ability to extract from files/text. The orchestration logic (extract→check→save) still exists only inside `telegram_bot.py`. Complexity is concentrated and partly duplicated — positive signal for a Seam. |
| **Proposed solution direction** | Introduce an Application Module that owns the use cases: record expense from extraction, handle correction attempt. The Telegram Adapter becomes a thin translator: PTB update → call use-case Module → format response from result. The use-case Module depends on `ports/` (ExtractionPort, ExpenseRepositoryPort) and `domain/` but has zero PTB imports. The CLI adapter calls the same Module instead of duplicating the pipeline. |
| **Locality benefit** | The correction loop (attempt counting, max-out check, refine→save→clear) lives in one place instead of inside a PTB handler. A bug in the correction flow is fixable without touching anything Telegram-related. |
| **Leverage benefit** | Telegram and CLI reuse the same existing Expense-recording behavior. Future driving Adapters can call the same workflow without duplicating orchestration. |
| **Testing benefit** | Workflow tests need zero PTB mocks. Correction permutations (complete, partial, maxed out, and resolved) are testable through the use-case Interface. |
| **Dependencies** | Designed together with ARCH-002 because the driving Interface is the test surface. |
| **ADR impact** | Aligns with ADR 0001's hexagonal intent; the precise relationship to ports is handled by ARCH-002. |
| **Completion criteria** | Telegram and CLI share one implementation of their existing Extraction-to-save behavior while preserving Adapter-specific input and metadata. Telegram-specific Correction behavior is owned outside PTB handlers. No new CLI behavior is required. |
| **Evidence required** | Existing Telegram and CLI behavior remains covered. New workflow tests cover complete and partial Extraction plus Correction resolution, retry, and maximum-attempt outcomes without PTB types. Thin Adapter tests cover translation and rendering. |

---

### ARCH-002: Driving Interface Ownership / ADR 0001 Clarification

| Field | Value |
|-------|-------|
| **Priority** | P0 (designed alongside ARCH-001) |
| **Status** | `Not started` |
| **Files/Symbols** | `src/expense_report/ports/` (only `extraction.py` and `repository.py` exist — both driven); `docs/adr/0001-initial-architecture.md` |
| **Problem** | ADR 0001 requires "Every adapter must implement a port protocol defined in `src/expense_report/ports/`." This requirement works for driven adapters (ExtractionPort, ExpenseRepositoryPort each have one Implementation each — hypothetical Seam until a second Adapter appears). But driving-side use-case Protocols do not exist at all. Without them, the Telegram Adapter has no port Interface to call into — it calls the concrete orchestration logic directly. ADR 0001's wording describes the driven-side relationship; applying it literally to driving adapters would require them to **implement** a port Protocol, which contradicts hexagonal convention (driving adapters **call into** ports, they don't implement them). This tension should be resolved either by clarifying ADR 0001 or creating a separate convention for driving-side Protocols. |
| **Deletion test** | Delete `ports/`. Callers would depend directly on concrete outbound Adapters; that coupling would become visible in the import graph, static checks, and tests. The PTB framework would remain the only inbound interaction point. |
| **Proposed solution direction** | As the Application Module from ARCH-001 takes shape, one or more driving-side use-case Protocols in `ports/` will naturally emerge — the Module exposes them, inbound adapters depend on them. Design these Protocols alongside the Application Module rather than in isolation. Clarify ADR 0001 to distinguish driving-side (adapter consumes the port) from driven-side (adapter implements the port) relationships. |
| **Locality benefit** | Changing a use case's Interface definition is confined to `ports/` and its single Implementation. No inbound adapter needs to change unless its calling signature changes. |
| **Leverage benefit** | A future Slack Adapter calls the same Interface. A test harness calls the same Interface. No duplicated orchestration knowledge. |
| **Testing benefit** | Use-case tests import Protocols and a fake or real Application Module. No inbound-adapter mocks needed. |
| **Dependencies** | ARCH-001 (Application Module) must exist first or concurrently — the Protocols need an Implementation. |
| **ADR impact** | **Contradicts ADR 0001's current wording** ("every adapter must implement a port protocol") when applied literally to inbound adapters. Recommend clarifying ADR 0001 to distinguish driving-side (adapter consumes) from driven-side (adapter implements) port relationships. |
| **Completion criteria** | Existing Telegram and CLI behavior is unchanged while shared orchestration is exercised through an application-owned driving Interface. ADR 0001 is updated or superseded to describe accurately how driving and driven Adapters relate to ports. |
| **Evidence required** | Workflow tests exercise the same driving Interface used by the inbound Adapters without PTB or argparse types. Narrow Adapter tests prove transport translation remains intact. The accepted ADR reflects the implemented dependency direction. |

---

### ARCH-003: Expense Browsing / Reporting Policy

| Field | Value |
|-------|-------|
| **Priority** | P1 |
| **Status** | `Not started` |
| **Files/Symbols** | `src/expense_report/adapters/inbound/telegram_bot.py`: `_format_month_view`, `_format_year_view`, `_build_list_keyboard`, `_make_list_handler`, `_make_list_callback_handler`, `_make_report_handler`, `_make_delete_callback_handler`, `_make_delete_handler` |
| **Problem** | Browse (`/list`), report (`/report`), and delete (`/delete`) behavior is implemented entirely inside the Telegram Adapter. The `/list` flow interleaves Telegram callback/keyboard work with year/month discovery, active-period selection, Currency aggregation, and Expense retrieval. `/report` combines current-month selection and retrieval with CSV/document delivery. `/delete` combines command/callback translation and rendering with the application action. These flows need not share one policy shape, but each currently lacks an independently testable application Interface. |
| **Deletion test** | Delete these handlers and any future driving Adapter that needs equivalent Expense browsing or reporting must reconstruct the same policy from repository calls. Because Telegram is currently the only production Adapter for these capabilities, this is still a hypothetical Seam and should be deepened only where policy can be separated cleanly from Telegram presentation. |
| **Proposed solution direction** | Concentrate browsing, reporting, and deletion policy in deeper application Modules. Keep callback-string decoding, keyboards, Telegram text, `BytesIO`, and message delivery in the Telegram Adapter. Decide the exact Module shape during the item-specific grilling session. |
| **Locality benefit** | Period selection, Currency aggregation, and Expense retrieval policy become verifiable together, while Telegram presentation remains local to the Adapter. |
| **Leverage benefit** | Another driving Adapter could reuse browsing and reporting policy without inheriting Telegram callback or keyboard knowledge. |
| **Testing benefit** | Policy tests exercise application outcomes without PTB mocks; narrow Adapter tests continue to verify callback decoding and rendering. |
| **Dependencies** | Preferably follows ARCH-001 and ARCH-002 so it can use the established application Module and Interface conventions. |
| **ADR impact** | None identified. |
| **Completion criteria** | Browsing/reporting policy is testable without PTB types, while Telegram-specific decoding and rendering remain in the Telegram Adapter. Existing `/list`, `/report`, and `/delete` behavior is preserved. |
| **Evidence required** | Existing pytest and Behave scenarios pass. New policy tests cover period selection and multi-Currency results; Adapter tests cover Telegram callbacks, keyboards, and document delivery. |

---

### ARCH-004: Composition / Configuration Without a Seam

| Field | Value |
|-------|-------|
| **Priority** | P1 or P2 |
| **Status** | `Not started` |
| **Files/Symbols** | `src/expense_report/adapters/inbound/main.py`: `main()` — instantiates `DspyExtractionAdapter()`, `SqliteExpenseRepository(db_path)`, `CorrectionStore()`, `UnauthorizedAttemptAudit(path)`, `Application.builder().token(token).build()`. `src/expense_report/adapters/inbound/cli_extraction.py`: `main()` — instantiates `DspyExtractionAdapter()`, `SqliteExpenseRepository(args.db)` |
| **Problem** | `main.py` is a legitimate Telegram composition root, but configuration knowledge is distributed. It reads Telegram and database values; authorization reads its own environment value; `DspyExtractionAdapter` reads LLM values during construction and reads them again in the image call; the CLI separately constructs concrete driven Adapters. Required values and failure modes are therefore not visible in one place per process. |
| **Deletion test** | Delete `main.py` and environment access still remains in authorization and extraction Modules; delete the CLI construction and the Telegram composition remains. The current composition root does not concentrate configuration knowledge. |
| **Proposed solution direction** | Validate configuration at each process entry point and pass explicit values into Adapters. Share parsing only where Telegram and CLI truly have the same configuration semantics. Keep concrete Adapter selection close to each entry point. |
| **Locality benefit** | Required startup values, defaults, and validation failures become visible in one place per process. |
| **Leverage benefit** | Adapters can be constructed predictably in production and tests without hidden environment reads. |
| **Testing benefit** | Configuration parsing and Adapter construction can be tested without repeatedly patching process-wide environment state. |
| **Dependencies** | Independent of the application Module reorganisation, though completing it afterwards may avoid rewiring twice. |
| **ADR impact** | Must preserve ADR 0004's requirement that logging is configured at the process entry point. |
| **Completion criteria** | Each executable validates its configuration once; driven Adapters receive explicit configuration; repeated LLM environment reads are removed; concrete Adapter selection remains in a clear composition root. |
| **Evidence required** | Startup/configuration tests cover required values, defaults, and invalid values. Telegram and CLI behavior remain unchanged. |

---

### ARCH-005: Domain Placement of CorrectionStore and CSV Serialization

| Field | Value |
|-------|-------|
| **Priority** | P2 (conditional — address when second implementation becomes concrete) |
| **Status** | `Not started` |
| **Files/Symbols** | `src/expense_report/domain/correction_state.py`: `CorrectionStore` (in-memory dict-based store with `set`/`get`/`remove` and a TODO about persistence); `src/expense_report/domain/csv_generator.py`: `generate_csv()` |
| **Problem** | Two domain-placement questions have arisen but neither requires action yet. **CorrectionStore**: `domain/correction_state.py` contains `PendingCorrection` (a pure domain entity with `user_id`, `original_result`, `attempt_count`, `maxed_out` invariant) — correctly in domain. `CorrectionStore` is an in-memory `dict[int, PendingCorrection]` with a TODO comment about future persistence. This is semantically a repository-like concept ("store and retrieve pending corrections by user_id") embedded in domain. A future Redis or database backend would create a second Implementation, which could justify introducing a purpose-named Interface at a new Seam. Until that future becomes concrete, the single in-memory Implementation is acceptable in its current location. **CSV generation**: `generate_csv` is a pure function with no external side effects and only stdlib dependencies, but CSV is an output-format serialization policy. Its placement in domain is technically permissible but debatable — if multiple output formats emerge (JSON, XLSX) or if CSV formatting needs adapter-specific framing (headers, metadata), it may belong with the presentation/policy layer instead. |
| **Deletion test** | Delete `CorrectionStore` from domain. The concept "store pending corrections" must be recreated. If a Protocol is defined, the in-memory Implementation moves out of domain. `PendingCorrection` entity stays. Delete `generate_csv` from domain. CSV generation must be recreated wherever output formatting lives — possibly in the new presentation Module from ARCH-003. |
| **Proposed solution direction** | Revisit `CorrectionStore` ownership while designing ARCH-001. Do not introduce a new Seam unless another Implementation or a clear independent variation is concrete. Revisit CSV ownership while designing ARCH-003, distinguishing Expense Report policy from output serialization. Record the resulting ownership rationale if it is load-bearing for future reviews. |
| **Locality benefit** | Correction state can live with the workflow that owns its lifecycle, and Expense Report serialization can live with the Module that owns output-format knowledge. Delaying a new Seam avoids speculative churn. |
| **Leverage benefit** | If real variation appears later, a purpose-named Interface can provide reuse without forcing current callers to learn speculative abstractions. |
| **Testing benefit** | `PendingCorrection` invariants remain independently testable; workflow tests use the selected state Implementation; serialization tests remain independent of PTB. |
| **Dependencies** | CSV placement decision depends on ARCH-003 (browse/report design). CorrectionStore split depends on a concrete second Implementation appearing. |
| **ADR impact** | If either decision resolves to a permanent placement, record in a new ADR. |
| **Completion criteria** | Ownership of Correction state and CSV serialization is explicit and consistent with ARCH-001/ARCH-003. Any new Seam is justified by concrete variation; otherwise current placement is either retained with rationale or changed without speculative Interfaces. |
| **Evidence required** | Existing tests pass after any move. Tests remain focused on the owning Module's Interface. Record an ADR only when the decision is sufficiently load-bearing to prevent repeated reconsideration. |

---

### ARCH-006: Extraction Implementation / ADR 0002 Mismatch

| Field | Value |
|-------|-------|
| **Priority** | P2 |
| **Status** | `Not started` |
| **Files/Symbols** | `docs/adr/0002-dspy-for-extraction.md`; `src/expense_report/adapters/out/dspy_extraction.py`: `ExpenseImageSignature`, `_DATE_RE`, `_image_extractor`, `_call_image_with_retry`, `_call_text_with_retry`, `_parse_direct_response` |
| **Problem** | ADR 0002 states that every Extraction call goes through dSPy machinery. Text Extraction and Correction do; image Extraction bypasses dSPy and calls the OpenAI-compatible client directly because of the documented context-window constraint. `ExpenseImageSignature` and `_image_extractor` remain constructed but are unused by the production image path, while `_DATE_RE` is unused. The Interface remains useful, but the Implementation and accepted decision disagree. |
| **Deletion test** | Delete `ExpenseImageSignature`, `_image_extractor`, and `_DATE_RE`; the production image path remains, while tests coupled to constructor internals would need adjustment. Replacing dSPy entirely would be a separate design and dependency decision because text Extraction and Correction currently rely on it. |
| **Proposed solution direction** | First decide whether the direct image path is an intentional exception or whether all Extraction must return to dSPy. Make ADR 0002 match that decision and remove unreachable or unjustified leftovers. Consolidating all paths on direct calls is a larger alternative that requires separate design and approval before removing a dependency. |
| **Dependencies** | None — documentation fix, with optional dependency cleanup. |
| **ADR impact** | Directly amends or supersedes ADR 0002. |
| **Completion criteria** | ADR 0002 describes the actual code paths accurately. Dead or unreachable code (`ExpenseImageSignature` if the direct path stays) is removed or justified. |
| **Evidence required** | Updated ADR text matches the actual code paths. All extraction tests pass. |

---

## 6. Recommended Execution Order

```
Iteration 1 (P0)
  ├── ARCH-001: Expense recording and Correction orchestration
  │       (Application Module — includes CLI duplication as evidence)
  └── ARCH-002: Driving Interface ownership / ADR 0001 clarification
          (designed alongside ARCH-001)

Iteration 2 (P1 — consequence of I1)
  └── ARCH-003: Expense browsing / reporting policy
          (formatting + orchestration extracted from Telegram)

Iteration 3 (P1 or P2 — independent)
  └── ARCH-004: Composition / configuration Module
          (config parsing + composition root)

Iteration 4 (P2 — conditional, independent)
  ├── ARCH-005: Domain placement (CorrectionStore + CSV serialization)
  └── ARCH-006: ADR 0002 reconciliation (extraction paths)
```

**Rationale:** ARCH-001 and ARCH-002 together define the central Seam. Until they exist, ARCH-003 has nothing to delegate to. ARCH-004 is independent and can be interleaved if capacity allows. ARCH-005 and ARCH-006 are conditional/lower-urgency and can happen at any time.

---

## 7. Status Legend & Update Instructions

### Legend (same as section 5)

| Status | Meaning |
|--------|---------|
| `Not started` | Not yet addressed. |
| `In progress` | Being worked in current iteration. |
| `Resolved` | Fix merged to `main`. |
| `Deferred` | Deliberately postponed; ADR or decision log entry exists. |
| `Wontfix` | Closed as not worth pursuing; ADR or decision log entry exists. |

### Update Procedure

After completing an item:
1. Change its `Status` field in the checklist entry.
2. Append a decision log entry (section 8) with: date, item ID, short summary, ADR number (if any).
3. If a new ADR was created, update any ADR-related notes in the checklist entry.
4. Remove or check off the item from the "Recommended Execution Order" section.
5. Return the document to the repository at `docs/architecture/hexagonal-alignment-todo.md`.

---

## 8. Decision Log

| Date | Item | Decision | ADR |
|------|------|----------|-----|
| | | | |

*No entries yet. Append here each time an ARCH item is resolved, deferred, or closed.*

---

*Document generated 2026-07-21. Last reviewed: 2026-07-21.*
*Next review: after any ARCH item changes status.*
