"""Application-owned driving Interface for Expense Recording."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from expense_report.domain.models import Expense, ExtractionResult
from expense_report.domain.source_types import SourceType


class RecordingMode(Enum):
    """Interaction semantics requested by a driving Adapter."""

    ONE_SHOT = "one_shot"
    CONVERSATIONAL = "conversational"


@dataclass(frozen=True)
class RecordExpense:
    """Transport-neutral command to record an Expense."""

    user_id: int
    source: str | bytes
    source_type: SourceType
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


@dataclass(frozen=True)
class CorrectionOpened:
    """Incomplete Extraction in CONVERSATIONAL mode; pending Correction state opened."""

    extraction: ExtractionResult


@dataclass(frozen=True)
class CorrectionResolved:
    """Correction refined to completion; Expense saved; state cleared."""

    expense: Expense
    extraction: ExtractionResult


@dataclass(frozen=True)
class CorrectionStillIncomplete:
    """Correction refined but still incomplete; attempt count incremented."""

    extraction: ExtractionResult
    attempt_count: int


@dataclass(frozen=True)
class CorrectionLimitReached:
    """Maximum Correction attempts exhausted; state cleared; nothing persisted."""


@dataclass(frozen=True)
class SourceRejected:
    """Raw source was rejected during preparation; nothing extracted or persisted."""

    reason: str


RecordingOutcome = (
    ExpenseRecorded
    | ExtractionIncomplete
    | CorrectionOpened
    | CorrectionResolved
    | CorrectionStillIncomplete
    | CorrectionLimitReached
    | SourceRejected
)


@runtime_checkable
class ExpenseRecordingPort(Protocol):
    """Driving Interface for the Expense Recording conversation."""

    def record(self, command: RecordExpense) -> RecordingOutcome:
        """Extract and, when complete, persist one Expense.

        Routes a conversational text command through the Correction lifecycle
        when a Correction is pending for the user.
        """
        ...
