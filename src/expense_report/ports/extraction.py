"""Port interface for expense extraction from receipts and free-text."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from expense_report.domain.models import ExtractionResult
from expense_report.ports.source_preparation import SourceView


@runtime_checkable
class ExtractionPort(Protocol):
    """Protocol for extracting structured expense data from a normalized source.

    Implementations may use dSPy, direct LLM calls, or any other mechanism.
    """

    def extract(
        self,
        source: SourceView,
        current_date: date | None = None,
    ) -> ExtractionResult:
        """Extract structured expense data from the given normalized source.

        Args:
            source: A neutral SourceView — free text or ordered page-image bytes.
            current_date: The date to treat as "today" when the source does not
                mention one. Defaults to today in the server's timezone.

        Returns:
            ExtractionResult with whatever fields could be extracted.
        """
        ...

    def refine(
        self,
        original: ExtractionResult,
        correction_text: str,
        current_date: date | None = None,
    ) -> ExtractionResult:
        """Refine a partial extraction using the user's correction text.

        Takes the original partial extraction result and the user's
        correction/amendment text, merges them to produce a more complete
        extraction result.

        Args:
            original: The partial extraction result from the original source.
            correction_text: The user's free-text correction/amendment.
            current_date: The date used to resolve relative date references
                (e.g. "yesterday", "last Monday") in the correction text.
                Defaults to today in the server's timezone.

        Returns:
            A refined ExtractionResult that should be more complete.
        """
        ...
