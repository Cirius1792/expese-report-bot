"""Driven port for normalizing a raw expense source into a neutral SourceView.

A SourceView is a ports-boundary DTO (not a domain entity): it carries only
free text or raw ordered page-image bytes — never base64, LLM chat parts,
PDFium objects, or resize/model metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from expense_report.domain.source_types import SourceType


@dataclass(frozen=True)
class FreeTextSourceView:
    """A normalized free-text expense source."""

    text: str


@dataclass(frozen=True)
class ReceiptPagesSourceView:
    """A normalized receipt source as ordered page-image bytes.

    One entry per page, in page order. For a photo this holds exactly one
    entry (the original byte string, undecoded).
    """

    page_images: tuple[bytes, ...]


SourceView = FreeTextSourceView | ReceiptPagesSourceView


class SourcePreparationError(Exception):
    """Raised when a raw source cannot be normalized into a SourceView.

    Carries a user-facing ``message`` suitable for rendering to the user.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@runtime_checkable
class SourcePreparationPort(Protocol):
    """Protocol for converting a raw upload into a neutral SourceView."""

    def prepare(self, source: str | bytes, source_type: SourceType) -> SourceView:
        """Normalize the raw source for the given source type.

        Args:
            source: The raw input — text (str) or bytes (image/PDF upload).
            source_type: Indicates whether source is text, an image, or a PDF.

        Returns:
            A SourceView carrying free text or ordered page-image bytes.

        Raises:
            SourcePreparationError: When the source cannot be normalized
                (e.g., a PDF with more than the supported page count).
        """
        ...
