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
