# Expense Recording Architecture — Design

**Date:** 2026-07-21
**Status:** Approved direction; awaiting written-spec review
**Scope:** ARCH-001 and the driving-Interface decision in ARCH-002, implemented first as a complete free-text tracer slice through Telegram and CLI.

## Goal

Concentrate shared Expense Recording orchestration in an application Module so driving Adapters translate transport input and render outcomes without invoking Extraction or constructing and saving Expenses themselves.

The first tracer slice proves the new Seam with complete free-text Expense Recording through both existing driving Adapters. Receipt-photo and Correction paths remain unchanged until that slice is verified.

## Ownership Rule

Responsibilities are assigned by this rule:

- A driving Adapter owns translation between its transport and application concepts.
- The application Module owns workflow decisions that must remain consistent across driving Adapters.
- A driven Adapter performs an external capability through a purpose-named Interface and is invoked by the application Module.
- Presentation remains in the driving Adapter; application outcomes contain meaning rather than Telegram or CLI formatting.

A behavior belongs in the application Module when replacing Telegram with another driving Adapter would still require that behavior to remain consistent.

## Architecture

### Driving Interface

Introduce an application-owned driving Interface with one operation:

```python
class ExpenseRecordingPort(Protocol):
    def record(self, command: RecordExpense) -> RecordingOutcome: ...
```

Inbound Adapters consume this Interface. The application-layer `ExpenseRecordingUseCase` is its concrete Implementation. This clarifies ADR 0001: driven Adapters implement driven port Interfaces, while driving Adapters consume driving port Interfaces.

### Command

The command carries transport-neutral values:

```python
@dataclass(frozen=True)
class RecordExpense:
    user_id: int
    source: str | bytes
    source_type: Literal["image", "text"]
    mode: RecordingMode
    receipt_photo_id: str | None = None
```

```python
class RecordingMode(Enum):
    ONE_SHOT = "one_shot"
    CONVERSATIONAL = "conversational"
```

Mode describes interaction semantics, not transport technology:

- `ONE_SHOT`: an incomplete Extraction is returned without opening Correction state. The CLI uses this mode.
- `CONVERSATIONAL`: incomplete Extraction may open or continue the existing Correction lifecycle. Telegram uses this mode.

The first tracer slice exercises complete text Extraction only, so both modes have the same successful path. Their different incomplete behavior is implemented only when the later partial/Correction slice moves behind the Seam.

### Outcomes

Use a typed, transport-neutral outcome union. The complete tracer slice requires:

```python
@dataclass(frozen=True)
class ExpenseRecorded:
    expense: Expense
    extraction: ExtractionResult
```

The completed ARCH-001 design will also need outcomes equivalent to:

- incomplete one-shot Extraction;
- Correction required or still incomplete;
- Correction limit reached.

Those outcomes will be finalized in the later partial/Correction slice rather than speculated into the first implementation.

### Expense Recording Use Case

`ExpenseRecordingUseCase` is the application-layer Implementation of `ExpenseRecordingPort`. It depends on:

- `ExtractionPort` for Extraction and later Correction refinement;
- `ExpenseRepositoryPort` for persistence;
- the existing in-process Correction state when the Correction slice is migrated.

It owns:

- choosing `extract()` or, later, `refine()` according to mode and pending state;
- interpreting Extraction completeness;
- constructing `Expense`;
- assigning `created_at` when the complete Expense is recorded;
- saving through `ExpenseRepositoryPort`;
- later, the Correction lifecycle and state transitions.

It has no PTB, argparse, filesystem, stdout, or rendering dependencies.

No new port is introduced for Correction state. Its single in-memory Implementation remains an internal application dependency until concrete variation justifies another Seam.

### Driving Adapters

Telegram retains:

- PTB handler registration and filters;
- `Update` and context translation;
- Receipt download and Telegram file identifiers;
- message, keyboard, and callback rendering.

CLI retains:

- argparse;
- file reading;
- stdout formatting;
- process-specific composition.

For complete free text, both Adapters call `ExpenseRecordingPort.record()` and render `ExpenseRecorded` using their existing output format.

### Composition

Each executable constructs `ExpenseRecordingUseCase` from the existing driven Adapters and passes it to the driving Adapter through `ExpenseRecordingPort`.

The concrete dependency direction is:

```text
Telegram Adapter ──┐
                   ├──> ExpenseRecordingPort <── ExpenseRecordingUseCase
CLI Adapter ───────┘                                  │
                                                      ├──> ExtractionPort
                                                      └──> ExpenseRepositoryPort
```

The Telegram composition root may continue passing `ExpenseRepositoryPort` separately to browse, report, and delete handlers; those workflows belong to later tracker items.

## First Tracer Slice

### Included

A complete free-text message or CLI argument:

1. is translated by the driving Adapter into `RecordExpense`;
2. crosses the new driving Seam;
3. invokes `ExtractionPort.extract(source, "text")` in `ExpenseRecordingUseCase`;
4. produces a complete `ExtractionResult`;
5. is converted to an `Expense` with the existing `user_id`, `receipt_photo_id=None`, and recording-time `created_at` behavior;
6. is saved through `ExpenseRepositoryPort`;
7. returns `ExpenseRecorded`;
8. is rendered by the originating Adapter exactly as before.

Both Telegram and CLI use the same `ExpenseRecordingUseCase` Implementation, proving real Leverage across two driving Adapters.

### Explicitly deferred

- Receipt-photo migration.
- Partial Extraction migration.
- Correction routing and state migration.
- Correction attempt semantics.
- New user-visible behavior.
- New infrastructure failure recovery.
- Browsing, reporting, and deletion orchestration.
- Configuration consolidation.

During the tracer slice, unchanged paths may continue using their current dependencies. Temporary mixed wiring is acceptable only as an intermediate state recorded in the implementation plan.

## Failure Behavior

The first slice preserves existing behavior:

- Extraction exceptions propagate.
- Repository exceptions propagate.
- The application Module does not invent generic failure outcomes or recovery policy.
- `ExpenseRecorded` is returned only after repository persistence succeeds.

Transport-specific logging or rendering of unexpected failures is outside ARCH-001.

## Alternatives Considered

### Input-shaped methods

`submit_receipt()` and `submit_text()` provide a small Interface but name input forms rather than the application purpose and make CLI Correction semantics implicit.

### Explicit routing methods

`record()`, `has_pending_correction()`, and `correct()` expose more flexibility but leak workflow ordering and Correction-state knowledge into driving Adapters, reducing Locality.

### Mode-aware recording operation — chosen

One `record()` operation keeps routing and orchestration behind the Seam while making the intentional one-shot versus conversational distinction explicit. It provides the greatest Depth and keeps both driving Adapters on the same Interface.

## Testing Strategy

### Application workflow tests

Add tests through `ExpenseRecordingPort` without PTB or argparse types. For the first slice, prove:

- complete one-shot text records an Expense;
- complete conversational text records an Expense when no Correction is pending;
- the saved Expense preserves extracted fields and User identity;
- the Module invokes Extraction and persistence in the expected successful flow;
- extraction and repository exceptions propagate.

### Thin Adapter tests

Preserve and narrow existing Adapter tests to prove:

- Telegram translates free text and `user_id` into the command and renders the existing save confirmation;
- CLI translates arguments into the command and prints its existing Extraction and saved-Expense output;
- neither Adapter constructs or saves the Expense in this migrated path.

### Regression evidence

After every implementation change, execute:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

The complete ARCH-001 migration must additionally retain existing photo and Correction coverage and add PTB-free workflow tests for partial Extraction, Correction resolution, retry, and maximum-attempt outcomes.

## Completion Boundary

The first tracer slice is successful when complete free-text recording in Telegram and CLI shares one `ExpenseRecordingUseCase` Implementation and all existing behavior remains covered.

ARCH-001 itself remains in progress until Receipt-photo and Telegram Correction orchestration also move behind the driving Interface and the required evidence in the architecture tracker is satisfied.
