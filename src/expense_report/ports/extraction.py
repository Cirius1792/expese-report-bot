"""Port interface for expense extraction from receipts and free-text."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from expense_report.domain.models import ExtractionResult
from expense_report.ports.source_preparation import SourceView


@runtime_checkable
class ExtractionPort(Protocol):
    """Protocol for extracting structured expense data from a normalized source.

    Implementations may use dSPy, direct LLM calls, or any other mechanism.
    """

    def extract(self, source: SourceView) -> ExtractionResult:
        """Extract structured expense data from the given normalized source.

        Args:
            source: A neutral SourceView — free text or ordered page-image bytes.

        Returns:
            ExtractionResult with whatever fields could be extracted.
        """
        ...

    def refine(
        self,
        original: ExtractionResult,
        correction_text: str,
    ) -> ExtractionResult:
        """Refine a partial extraction using the user's correction text.

        Takes the original partial extraction result and the user's
        correction/amendment text, merges them to produce a more complete
        extraction result.

        Args:
            original: The partial extraction result from the original source.
            correction_text: The user's free-text correction/amendment.

        Returns:
            A refined ExtractionResult that should be more complete.
        """
        ...
