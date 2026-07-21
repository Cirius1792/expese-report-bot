# Expense Recording Free-Text Tracer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route complete and incomplete free-text Expense Recording from Telegram and CLI through one application-owned `ExpenseRecordingPort` implemented by `ExpenseRecordingUseCase`, while preserving all existing user-visible behavior.

**Architecture:** Add transport-neutral commands, modes, and outcomes beside the new driving Protocol in `ports/expense_recording.py`; implement orchestration in `application/expense_recording.py` using the existing Extraction and repository driven ports. Telegram and CLI translate their inputs into `RecordExpense`, call the driving Interface, and retain presentation plus temporary incomplete/Correction handling. Receipt-photo and pending-Correction orchestration remain on the legacy path.

**Tech Stack:** Python 3.12+, frozen dataclasses, `Enum`, `Protocol`, pytest, `unittest.mock`, Ruff, ty, uv.

## Global Constraints

- Follow `AGENTS.md`, `CONTEXT.md`, ADR 0001, and ADR 0006.
- The approved design is `docs/superpowers/specs/2026-07-21-expense-recording-architecture-design.md`.
- Write EDD expectations before implementation and implement red-first.
- Do not add dependencies or change existing driven port Interfaces.
- Do not migrate Receipt-photo or pending-Correction orchestration in this slice.
- Preserve Telegram and CLI rendering exactly.
- Keep ARCH-001 `In progress`; do not update the architecture tracker to `Resolved`.
- After every file-changing task, run exactly `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest` and retain the actual output.
- Commit through the installed gitleaks pre-commit hook; never bypass it.

## File Structure

- Create `docs/expectations/expense-recording-free-text-tracer.md` — executable behavior contract and evidence slots for this slice.
- Create `src/expense_report/ports/expense_recording.py` — driving command, mode, outcomes, union, and Protocol.
- Create `src/expense_report/application/__init__.py` — application package marker.
- Create `src/expense_report/application/expense_recording.py` — framework-independent `ExpenseRecordingUseCase`.
- Create `tests/application/__init__.py` — application test package marker.
- Create `tests/application/test_expense_recording.py` — PTB/argparse-free workflow tests.
- Modify `src/expense_report/adapters/inbound/telegram_bot.py` — free-text translation and outcome rendering; retain photo and pending-Correction legacy paths.
- Modify `src/expense_report/adapters/inbound/main.py` — Telegram composition of `ExpenseRecordingUseCase`.
- Modify `tests/adapters/inbound/test_telegram_bot.py` — thin free-text Adapter tests and legacy regression assertions.
- Modify `tests/adapters/inbound/test_logging_config.py` — composition-order evidence for the new use case.
- Modify `src/expense_report/adapters/inbound/cli_extraction.py` — free-text translation and outcome rendering; retain image legacy path.
- Modify `tests/adapters/inbound/test_cli_extraction.py` — thin command-translation test and sociable regression test.

---

### Task 1: Capture EDD Expectations Before Implementation

**Files:**
- Create: `docs/expectations/expense-recording-free-text-tracer.md`

**Interfaces:**
- Consumes: approved design and ADR 0006.
- Produces: explicit expectations that Tasks 2–4 must prove.

- [ ] **Step 1: Write the expectation document**

```markdown
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
```

- [ ] **Step 2: Run the mandatory verification chain**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: formatter reports the current files unchanged, Ruff and ty pass, and the baseline suite reports 178 passing tests.

- [ ] **Step 3: Commit the expectations**

```bash
git add docs/expectations/expense-recording-free-text-tracer.md
git commit -m "docs: define free-text expense recording expectations"
```

Expected: gitleaks pre-commit hook passes and only the expectation file is committed.

---

### Task 2: Add the Driving Interface and Application Use Case

**Files:**
- Create: `src/expense_report/ports/expense_recording.py`
- Create: `src/expense_report/application/__init__.py`
- Create: `src/expense_report/application/expense_recording.py`
- Create: `tests/application/__init__.py`
- Create: `tests/application/test_expense_recording.py`

**Interfaces:**
- Consumes:
  - `ExtractionPort.extract(source: str | bytes, source_type: Literal["image", "text"]) -> ExtractionResult`
  - `ExpenseRepositoryPort.save(expense: Expense) -> Expense`
- Produces:
  - `RecordingMode.ONE_SHOT` and `RecordingMode.CONVERSATIONAL`
  - `RecordExpense(user_id: int, source: str | bytes, source_type: Literal["image", "text"], mode: RecordingMode, receipt_photo_id: str | None = None)`
  - `ExpenseRecorded(expense: Expense, extraction: ExtractionResult)`
  - `ExtractionIncomplete(extraction: ExtractionResult)`
  - `RecordingOutcome = ExpenseRecorded | ExtractionIncomplete`
  - `ExpenseRecordingPort.record(command: RecordExpense) -> RecordingOutcome`
  - `ExpenseRecordingUseCase(extraction: ExtractionPort, repository: ExpenseRepositoryPort)`

- [ ] **Step 1: Write the failing PTB-free workflow tests**

Create `tests/application/__init__.py` as an empty file and create `tests/application/test_expense_recording.py`:

```python
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from expense_report.domain.models import ExtractionResult
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort


def _complete_extraction() -> ExtractionResult:
    return ExtractionResult(
        amount=Decimal("15.00"),
        currency="EUR",
        merchant="Restaurant",
        date=date(2026, 7, 15),
        category="food",
    )


def _incomplete_extraction() -> ExtractionResult:
    return ExtractionResult(
        amount=Decimal("15.00"),
        currency="EUR",
        merchant=None,
        date=date(2026, 7, 15),
        category=None,
    )


@pytest.mark.parametrize("mode_name", ["ONE_SHOT", "CONVERSATIONAL"])
def test_complete_text_records_expense(mode_name: str) -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = lambda expense: replace(expense, id=41)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )
    command = RecordExpense(
        user_id=12345,
        source="lunch 15 eur",
        source_type="text",
        mode=RecordingMode[mode_name],
    )

    with patch("expense_report.application.expense_recording.datetime") as clock:
        clock.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
        outcome = use_case.record(command)

    assert isinstance(outcome, ExpenseRecorded)
    assert outcome.expense.id == 41
    assert outcome.expense.user_id == 12345
    assert outcome.expense.receipt_photo_id is None
    assert outcome.expense.created_at == datetime(2026, 7, 15, 12, 0, 0)
    assert outcome.extraction == _complete_extraction()
    extraction.extract.assert_called_once_with("lunch 15 eur", "text")
    repository.save.assert_called_once()


@pytest.mark.parametrize("mode_name", ["ONE_SHOT", "CONVERSATIONAL"])
def test_incomplete_text_returns_without_persisting(mode_name: str) -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExtractionIncomplete,
        RecordExpense,
        RecordingMode,
    )

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _incomplete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    outcome = use_case.record(
        RecordExpense(
            user_id=12345,
            source="lunch 15 eur",
            source_type="text",
            mode=RecordingMode[mode_name],
        )
    )

    assert outcome == ExtractionIncomplete(extraction=_incomplete_extraction())
    repository.save.assert_not_called()


def test_extraction_exception_propagates() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.side_effect = RuntimeError("extract failed")
    repository = MagicMock(spec=ExpenseRepositoryPort)
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    with pytest.raises(RuntimeError, match="extract failed"):
        use_case.record(
            RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT)
        )


def test_repository_exception_propagates() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import RecordExpense, RecordingMode

    extraction = MagicMock(spec=ExtractionPort)
    extraction.extract.return_value = _complete_extraction()
    repository = MagicMock(spec=ExpenseRepositoryPort)
    repository.save.side_effect = RuntimeError("save failed")
    use_case = ExpenseRecordingUseCase(
        cast(ExtractionPort, extraction),
        cast(ExpenseRepositoryPort, repository),
    )

    with pytest.raises(RuntimeError, match="save failed"):
        use_case.record(
            RecordExpense(12345, "lunch", "text", RecordingMode.ONE_SHOT)
        )
```

- [ ] **Step 2: Run the focused tests to prove RED**

Run:

```bash
uv run pytest tests/application/test_expense_recording.py -q
```

Expected: collection or execution fails with `ModuleNotFoundError: No module named 'expense_report.application'` or missing `expense_report.ports.expense_recording`.

- [ ] **Step 3: Add the driving Interface types**

Create `src/expense_report/ports/expense_recording.py`:

```python
"""Application-owned driving Interface for Expense Recording."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, Protocol, runtime_checkable

from expense_report.domain.models import Expense, ExtractionResult


class RecordingMode(Enum):
    """Interaction semantics requested by a driving Adapter."""

    ONE_SHOT = "one_shot"
    CONVERSATIONAL = "conversational"


@dataclass(frozen=True)
class RecordExpense:
    """Transport-neutral command to record an Expense."""

    user_id: int
    source: str | bytes
    source_type: Literal["image", "text"]
    mode: RecordingMode
    receipt_photo_id: str | None = None


@dataclass(frozen=True)
class ExpenseRecorded:
    """Successful Expense Recording result after persistence."""

    expense: Expense
    extraction: ExtractionResult


@dataclass(frozen=True)
class ExtractionIncomplete:
    """Incomplete Extraction that was deliberately not persisted."""

    extraction: ExtractionResult


RecordingOutcome = ExpenseRecorded | ExtractionIncomplete


@runtime_checkable
class ExpenseRecordingPort(Protocol):
    """Driving Interface for the Expense Recording conversation."""

    def record(self, command: RecordExpense) -> RecordingOutcome:
        """Extract and, when complete, persist one Expense."""
        ...
```

Create empty package markers:

```bash
mkdir -p src/expense_report/application
: > src/expense_report/application/__init__.py
```

- [ ] **Step 4: Implement the smallest application use case**

Create `src/expense_report/application/expense_recording.py`:

```python
"""Application orchestration for Expense Recording."""

from __future__ import annotations

from datetime import datetime

from expense_report.domain.models import Expense
from expense_report.ports.expense_recording import (
    ExpenseRecorded,
    ExtractionIncomplete,
    RecordExpense,
    RecordingOutcome,
)
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort


class ExpenseRecordingUseCase:
    """Extract, validate completeness, construct, and persist an Expense."""

    def __init__(
        self,
        extraction: ExtractionPort,
        repository: ExpenseRepositoryPort,
    ) -> None:
        self._extraction = extraction
        self._repository = repository

    def record(self, command: RecordExpense) -> RecordingOutcome:
        result = self._extraction.extract(command.source, command.source_type)
        if not result.is_complete:
            return ExtractionIncomplete(extraction=result)

        assert result.amount is not None and result.currency is not None
        assert result.merchant is not None and result.date is not None
        expense = Expense(
            id=None,
            amount=result.amount,
            currency=result.currency,
            merchant=result.merchant,
            date=result.date,
            category=result.category,
            user_id=command.user_id,
            receipt_photo_id=command.receipt_photo_id,
            created_at=datetime.now(),
        )
        saved_expense = self._repository.save(expense)
        return ExpenseRecorded(expense=saved_expense, extraction=result)
```

- [ ] **Step 5: Run focused tests to prove GREEN**

Run:

```bash
uv run pytest tests/application/test_expense_recording.py -q
```

Expected: all parameterized application tests pass.

- [ ] **Step 6: Add explicit Protocol conformance evidence**

Append to `tests/application/test_expense_recording.py`:

```python
def test_use_case_satisfies_expense_recording_port() -> None:
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import ExpenseRecordingPort

    extraction = MagicMock(spec=ExtractionPort)
    repository = MagicMock(spec=ExpenseRepositoryPort)

    assert isinstance(
        ExpenseRecordingUseCase(
            cast(ExtractionPort, extraction),
            cast(ExpenseRepositoryPort, repository),
        ),
        ExpenseRecordingPort,
    )
```

- [ ] **Step 7: Run the mandatory verification chain**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: Ruff and ty pass; all baseline and new application tests pass. If Ruff reformats the files, inspect the changes and rerun the same full chain before committing.

- [ ] **Step 8: Commit the application Seam**

```bash
git add src/expense_report/ports/expense_recording.py \
  src/expense_report/application/__init__.py \
  src/expense_report/application/expense_recording.py \
  tests/application/__init__.py \
  tests/application/test_expense_recording.py
git commit -m "feat: add expense recording use case"
```

Expected: gitleaks passes; only the new application/port files and tests are committed.

---

### Task 3: Migrate Telegram Free Text and Compose the Use Case

**Files:**
- Modify: `src/expense_report/adapters/inbound/telegram_bot.py`
- Modify: `src/expense_report/adapters/inbound/main.py`
- Modify: `tests/adapters/inbound/test_telegram_bot.py`
- Modify: `tests/adapters/inbound/test_logging_config.py`

**Interfaces:**
- Consumes: all Task 2 types and `ExpenseRecordingPort.record(command) -> RecordingOutcome`.
- Produces:
  - `register_handlers(app, expense_recording, extraction_adapter, repository, correction_store) -> None`
  - New free-text commands use `RecordingMode.CONVERSATIONAL`.
  - Existing photo and pending-Correction branches continue to use `ExtractionPort`, `ExpenseRepositoryPort`, and `CorrectionStore` directly.

- [ ] **Step 1: Rewrite the complete free-text Adapter test to prove command translation**

In `tests/adapters/inbound/test_telegram_bot.py`, import the Task 2 outcomes and replace `TestTextHandler.test_complete_extraction_saves_and_confirms` with:

```python
    def test_complete_extraction_calls_use_case_and_confirms(self) -> None:
        """New text is translated to a conversational recording command."""
        from expense_report.adapters.inbound.telegram_bot import _make_text_handler
        from expense_report.ports.expense_recording import (
            ExpenseRecorded,
            RecordExpense,
            RecordingMode,
        )

        result = ExtractionResult(
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
        )
        saved = Expense(
            id=7,
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
            user_id=12345,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 20, 14, 0, 0),
        )
        recording = MagicMock()
        recording.record.return_value = ExpenseRecorded(saved, result)
        extraction = MagicMock()
        repository = MagicMock()
        store = CorrectionStore()
        handler = _make_text_handler(recording, extraction, repository, store)
        update = _make_update(text="coffee 12.50 usd")

        asyncio.run(handler(update, MagicMock()))

        recording.record.assert_called_once_with(
            RecordExpense(
                user_id=12345,
                source="coffee 12.50 usd",
                source_type="text",
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=None,
            )
        )
        extraction.extract.assert_not_called()
        repository.save.assert_not_called()
        assert "✅ Saved." in update.effective_message.reply_text.call_args[0][0]
        assert "12.50 USD" in update.effective_message.reply_text.call_args[0][0]
```

Replace the existing partial-text test with:

```python
    def test_partial_extraction_opens_existing_correction_state(self) -> None:
        """An incomplete outcome opens the existing Telegram Correction state."""
        from expense_report.adapters.inbound.telegram_bot import _make_text_handler
        from expense_report.ports.expense_recording import ExtractionIncomplete

        partial = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        recording = MagicMock()
        recording.record.return_value = ExtractionIncomplete(partial)
        extraction = MagicMock()
        repository = MagicMock()
        store = CorrectionStore()
        handler = _make_text_handler(recording, extraction, repository, store)
        update = _make_update(text="something")

        asyncio.run(handler(update, MagicMock()))

        repository.save.assert_not_called()
        pending = store.get(12345)
        assert pending is not None
        assert pending.original_result == partial
        reply = update.effective_message.reply_text.call_args[0][0]
        assert "partial information" in reply
        assert "amount" in reply
```

In the pending-Correction regression test, make these exact changes around handler construction and its assertions:

```python
        recording = MagicMock()
        handler = _make_text_handler(recording, adapter, repo, store)
        update = _make_update(text="EUR, Coffee Shop, 2026-07-20")
        context = MagicMock()

        asyncio.run(handler(update, context))

        recording.record.assert_not_called()
        adapter.refine.assert_called_once()
```

The rest of that test's existing Correction-state and rendering assertions remain intact. Replace `TestRegisterHandlers.test_registers_all_handlers` with:

```python
    def test_registers_all_handlers(self) -> None:
        from expense_report.adapters.inbound.telegram_bot import register_handlers

        app = MagicMock()
        recording = MagicMock()
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()

        register_handlers(app, recording, adapter, repo, store)

        assert app.add_handler.call_count == 8
```

- [ ] **Step 2: Run Telegram-focused tests to prove RED**

Run:

```bash
uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestTextHandler tests/adapters/inbound/test_telegram_bot.py::TestRegisterHandlers -q
```

Expected: failures report the old `_make_text_handler` and `register_handlers` signatures or that `record()` was not called.

- [ ] **Step 3: Make Telegram translate new text into the driving Interface**

In `src/expense_report/adapters/inbound/telegram_bot.py`:

1. Import `ExtractionResult` explicitly and import `ExpenseRecorded`, `ExtractionIncomplete`, `ExpenseRecordingPort`, `RecordExpense`, and `RecordingMode` from `expense_report.ports.expense_recording`.
2. Add `expense_recording: ExpenseRecordingPort` as the second parameter of `register_handlers` and pass it as the first dependency to `_make_text_handler`.
3. Change `_make_text_handler` to this dependency signature while retaining the existing pending branch unchanged:

```python
def _make_text_handler(
    expense_recording: ExpenseRecordingPort,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
):
```

Replace only the new-expense branch after the pending-Correction return with:

```python
        logger.info("Text received from user %s", user_id)
        outcome = expense_recording.record(
            RecordExpense(
                user_id=user_id,
                source=text,
                source_type="text",
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=None,
            )
        )

        if isinstance(outcome, ExtractionIncomplete):
            result = outcome.extraction
            missing = _missing_fields(result)
            logger.info(
                "Partial extraction for user %s text: missing %s",
                user_id,
                ", ".join(missing),
            )
            correction_store.set(
                user_id,
                PendingCorrection(user_id=user_id, original_result=result),
            )
            await _reply_with_incomplete_extraction(update, result)
            return

        logger.info("Complete extraction for user %s text", user_id)
        await _reply_with_recorded_expense(update, outcome)
```

4. Extract presentation helpers without changing their strings or keyboard:

```python
async def _reply_with_recorded_expense(
    update: Update,
    outcome: ExpenseRecorded,
) -> None:
    if update.effective_message is None or update.effective_user is None:
        return

    result = outcome.extraction
    saved_expense = outcome.expense
    logger.info("Saved expense %s for user %s", saved_expense.id, update.effective_user.id)
    summary = (
        f"📄 *Extracted expense:*\n"
        f"Expense #{saved_expense.id}\n"
        f"Amount: {result.amount} {result.currency}\n"
        f"Merchant: {result.merchant}\n"
        f"Date: {result.date}\n"
        f"Category: {result.category or '—'}\n\n"
        f"✅ Saved."
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{saved_expense.id}")]]
    )
    await update.effective_message.reply_text(summary, reply_markup=keyboard)


async def _reply_with_incomplete_extraction(
    update: Update,
    result: ExtractionResult,
) -> None:
    if update.effective_message is None:
        return
    missing = _missing_fields(result)
    await update.effective_message.reply_text(
        f"I extracted partial information. Please reply with the"
        f" missing details: {', '.join(missing)}"
    )
```

5. Keep `_respond_to_extraction` for photo and Correction only. After it saves a complete legacy Extraction, call `_reply_with_recorded_expense(update, ExpenseRecorded(saved_expense, result))`; for an incomplete result call `_reply_with_incomplete_extraction(update, result)`. This removes duplicated rendering but does not move legacy orchestration.

- [ ] **Step 4: Compose the use case in Telegram main**

In `src/expense_report/adapters/inbound/main.py`, import `ExpenseRecordingUseCase`. After constructing `extraction` and `repository`, construct:

```python
    expense_recording = ExpenseRecordingUseCase(extraction, repository)
```

Call:

```python
    register_handlers(
        app,
        expense_recording,
        extraction,
        repository,
        correction_store,
    )
```

In `tests/adapters/inbound/test_logging_config.py`, patch `main_module.ExpenseRecordingUseCase` with a side effect that appends `"expense_recording_use_case"` and returns a `MagicMock`. Insert that value after `"repository"` in the expected call order. This proves composition occurs before handler registration.

- [ ] **Step 5: Run Telegram tests to prove GREEN**

Run:

```bash
uv run pytest tests/adapters/inbound/test_telegram_bot.py tests/adapters/inbound/test_logging_config.py -q
```

Expected: all Telegram Adapter and composition tests pass; photo and pending-Correction tests remain green.

- [ ] **Step 6: Run the mandatory verification chain**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: all checks and the full suite pass. Inspect Ruff formatting and rerun the full chain if it changed files.

- [ ] **Step 7: Commit the Telegram migration**

```bash
git add src/expense_report/adapters/inbound/telegram_bot.py \
  src/expense_report/adapters/inbound/main.py \
  tests/adapters/inbound/test_telegram_bot.py \
  tests/adapters/inbound/test_logging_config.py
git commit -m "refactor: route Telegram text through expense recording"
```

Expected: gitleaks passes; no Receipt-photo or Correction ownership migration is included.

---

### Task 4: Migrate CLI Free Text While Retaining the Image Path

**Files:**
- Modify: `src/expense_report/adapters/inbound/cli_extraction.py`
- Modify: `tests/adapters/inbound/test_cli_extraction.py`

**Interfaces:**
- Consumes: Task 2's `ExpenseRecordingUseCase` and driving types.
- Produces: CLI free text uses `RecordingMode.ONE_SHOT`; image extraction remains on the existing direct Extraction/repository path.

- [ ] **Step 1: Add a thin CLI command-translation test**

Append to `TestMainSociable` in `tests/adapters/inbound/test_cli_extraction.py`:

```python
    def test_text_flow_translates_arguments_to_record_command(self) -> None:
        from expense_report.domain.models import Expense, ExtractionResult
        from expense_report.ports.expense_recording import (
            ExpenseRecorded,
            RecordExpense,
            RecordingMode,
        )

        result = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
        )
        saved = Expense(
            id=9,
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Restaurant",
            date=date(2026, 7, 15),
            category="food",
            user_id=42,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 15, 12, 0, 0),
        )

        with (
            patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
            patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository"),
            patch(
                "expense_report.application.expense_recording.ExpenseRecordingUseCase"
            ) as use_case_class,
            patch(
                "sys.argv",
                [
                    "expense-extract",
                    "--user-id",
                    "42",
                    "extract-from-text",
                    "15 eur restaurant",
                ],
            ),
        ):
            use_case_class.return_value.record.return_value = ExpenseRecorded(saved, result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        use_case_class.return_value.record.assert_called_once_with(
            RecordExpense(
                user_id=42,
                source="15 eur restaurant",
                source_type="text",
                mode=RecordingMode.ONE_SHOT,
                receipt_photo_id=None,
            )
        )
```

Append this incomplete rendering test:

```python
    def test_text_flow_renders_incomplete_without_saving(
        self,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from expense_report.domain.models import ExtractionResult
        from expense_report.ports.expense_recording import ExtractionIncomplete

        result = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant=None,
            date=date(2026, 7, 15),
            category=None,
        )

        with (
            patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
            patch("expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository") as repo_class,
            patch(
                "expense_report.application.expense_recording.ExpenseRecordingUseCase"
            ) as use_case_class,
            patch(
                "sys.argv",
                ["expense-extract", "extract-from-text", "15 eur"],
            ),
        ):
            use_case_class.return_value.record.return_value = ExtractionIncomplete(result)
            from expense_report.adapters.inbound.cli_extraction import main

            main()

        captured = capsys.readouterr()
        assert "Complete: False" in captured.out
        assert "Extraction incomplete — not saved." in captured.out
        repo_class.return_value.save.assert_not_called()
```


- [ ] **Step 2: Run CLI-focused tests to prove RED**

Run:

```bash
uv run pytest tests/adapters/inbound/test_cli_extraction.py -q
```

Expected: the new tests fail because CLI free text still calls `extractor.extract` directly and does not instantiate `ExpenseRecordingUseCase`.

- [ ] **Step 3: Route only CLI free text through the use case**

In `src/expense_report/adapters/inbound/cli_extraction.py`:

Keep `datetime` and `Expense` imports because the explicitly deferred image path still constructs and saves an Expense. Replace `main()` with this implementation (imports remain lazy at the process boundary):

```python
def main() -> None:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    from expense_report.adapters.out.dspy_extraction import DspyExtractionAdapter
    from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository
    from expense_report.application.expense_recording import ExpenseRecordingUseCase
    from expense_report.ports.expense_recording import (
        ExpenseRecorded,
        RecordExpense,
        RecordingMode,
        RecordingOutcome,
    )

    extractor = DspyExtractionAdapter()
    repo = SqliteExpenseRepository(args.db)
    expense_recording = ExpenseRecordingUseCase(extractor, repo)
    outcome: RecordingOutcome | None = None

    if args.command == "extract-from-image":
        with open(args.image_path, "rb") as image_file:
            source = image_file.read()
        source_label = args.image_path
        result = extractor.extract(source, "image")
    else:
        source_label = args.text
        outcome = expense_recording.record(
            RecordExpense(
                user_id=args.user_id,
                source=args.text,
                source_type="text",
                mode=RecordingMode.ONE_SHOT,
                receipt_photo_id=None,
            )
        )
        result = outcome.extraction

    print(f"Extraction result from '{source_label}':")
    print(f"  Amount:   {result.amount}")
    print(f"  Currency: {result.currency}")
    print(f"  Merchant: {result.merchant}")
    print(f"  Date:     {result.date}")
    print(f"  Category: {result.category}")
    print(f"  Complete: {result.is_complete}")

    if isinstance(outcome, ExpenseRecorded):
        print(f"\nSaved expense: {outcome.expense}")
    elif outcome is not None:
        print("\nExtraction incomplete — not saved.")
    elif result.is_complete:
        assert result.amount is not None and result.currency is not None
        assert result.merchant is not None and result.date is not None
        expense = Expense(
            id=None,
            amount=result.amount,
            currency=result.currency,
            merchant=result.merchant,
            date=result.date,
            category=result.category,
            user_id=args.user_id,
            receipt_photo_id=None,
            created_at=datetime.now(),
        )
        saved = repo.save(expense)
        print(f"\nSaved expense: {saved}")
    else:
        print("\nExtraction incomplete — not saved.")
```

Update the existing sociable text test's clock patch target from `expense_report.adapters.inbound.cli_extraction.datetime` to `expense_report.application.expense_recording.datetime`. Leave the image test's existing CLI clock patch unchanged. This proves the application Module now owns recording time only for migrated text.

- [ ] **Step 4: Run CLI tests to prove GREEN**

Run:

```bash
uv run pytest tests/adapters/inbound/test_cli_extraction.py -q
```

Expected: parser, complete text, incomplete text, and image regression tests all pass with unchanged stdout assertions.

- [ ] **Step 5: Run the mandatory verification chain**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: Ruff and ty pass; the full suite passes, including unchanged image, photo, and Correction coverage.

- [ ] **Step 6: Commit the CLI migration**

```bash
git add src/expense_report/adapters/inbound/cli_extraction.py \
  tests/adapters/inbound/test_cli_extraction.py
git commit -m "refactor: route CLI text through expense recording"
```

Expected: gitleaks passes; only the CLI text path changes, while the image path remains legacy.

---

### Task 5: Record Executed EDD Evidence and Independently Review the Slice

**Files:**
- Modify: `docs/expectations/expense-recording-free-text-tracer.md`

**Interfaces:**
- Consumes: executed tests from Tasks 2–4 and the final repository state.
- Produces: explicit expectation-to-evidence mapping without marking ARCH-001 resolved.

- [ ] **Step 1: Run focused evidence commands**

Run:

```bash
uv run pytest tests/application/test_expense_recording.py -q
uv run pytest tests/adapters/inbound/test_telegram_bot.py::TestTextHandler -q
uv run pytest tests/adapters/inbound/test_cli_extraction.py -q
```

Expected: application workflow, Telegram translation/rendering, and CLI translation/rendering tests all pass. Copy the exact outputs into the expectation document's Evidence section.

- [ ] **Step 2: Run final mandatory verification**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: formatter is clean, Ruff and ty pass, and every pytest test passes. Copy the exact output into the Evidence section.

- [ ] **Step 3: Map every expectation to an executed test**

Replace the Evidence placeholder with a table using the exact final test node IDs. The completed table must map:

```markdown
| Expectation | Executed evidence |
|---|---|
| 1–2, 5, 8 | `tests/application/test_expense_recording.py` focused output and named workflow tests |
| 3, 6, 9, 11 | `tests/adapters/inbound/test_telegram_bot.py::TestTextHandler` focused output |
| 4, 7, 9 | `tests/adapters/inbound/test_cli_extraction.py` focused output |
| 10 | Passing existing photo tests plus diff review showing `_make_photo_handler` remains on driven ports |
| 12 | `docs/architecture/hexagonal-alignment-todo.md` still records ARCH-001 as `In progress` |
```

Below the table, paste the exact final command output in a fenced `text` block. Do not write “all green” without that output.

- [ ] **Step 4: Run verification after the evidence-document change**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest
```

Expected: the final repository state still passes every check; if counts differ from Step 2, record the latest output instead.

- [ ] **Step 5: Commit evidence only**

```bash
git add docs/expectations/expense-recording-free-text-tracer.md
git commit -m "docs: record expense recording tracer evidence"
```

Expected: gitleaks passes and only the expectation evidence changes.

- [ ] **Step 6: Request independent review**

Dispatch a `reviewer` subagent with the approved design, ADR 0006, this plan, the implementation commit range, and these audit questions:

```text
1. Do Telegram and CLI both call ExpenseRecordingPort for new free text?
2. Is Expense construction and persistence absent from both migrated free-text branches?
3. Are Receipt-photo and pending-Correction orchestration unchanged?
4. Does ExtractionIncomplete preserve existing Telegram and CLI behavior without speculative Correction outcomes?
5. Do application tests run without PTB or argparse types and cover both modes plus exception propagation?
6. Is ARCH-001 still In progress?
```

Expected: reviewer returns no unresolved correctness findings. If findings exist, add a red regression test first, apply the smallest fix through a worker, rerun the full verification chain, and update the evidence document with the latest output before claiming completion.
