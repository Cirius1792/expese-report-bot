"""Adapter that normalizes raw expense sources into neutral SourceViews.

Strategy dispatch on SourceType (the strategy). PDF rendering uses
pypdfium2 (scale 2, JPEG quality 92, pages in order). PDFs with more than
``MAX_PDF_PAGES`` pages, zero-page PDFs, and invalid PDF bytes are rejected
with a :class:`SourcePreparationError` carrying a user-facing message.
"""

from __future__ import annotations

import io
import logging

import pypdfium2 as pdfium

from expense_report.domain.source_types import SourceType
from expense_report.ports.source_preparation import (
    FreeTextSourceView,
    ReceiptPagesSourceView,
    SourcePreparationError,
    SourceView,
)

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 5
_PDF_RENDER_SCALE = 2
_PDF_JPEG_QUALITY = 92


class SourcePreparationAdapter:
    """Match on SourceType and convert a raw upload into a SourceView."""

    def prepare(self, source: str | bytes, source_type: SourceType) -> SourceView:
        """Normalize the raw source for the given source type."""
        match source_type:
            case SourceType.TEXT:
                assert isinstance(source, str), "Text source must be a string"
                return FreeTextSourceView(text=source)
            case SourceType.IMAGE:
                assert isinstance(source, bytes), "Image source must be bytes"
                return ReceiptPagesSourceView(page_images=(source,))
            case SourceType.PDF:
                assert isinstance(source, bytes), "PDF source must be bytes"
                return self._prepare_pdf(source)
        raise AssertionError(f"Unsupported source type: {source_type!r}")

    def _prepare_pdf(self, source: bytes) -> ReceiptPagesSourceView:
        """Render each PDF page in order into JPEG bytes; enforce the page cap."""
        try:
            document = pdfium.PdfDocument(source)
        except Exception as exc:
            logger.info("PDF could not be opened: %s", type(exc).__name__)
            raise SourcePreparationError(
                "The file could not be read as a PDF, so your request will not be"
                " satisfied. Please send a valid PDF file."
            ) from exc

        page_count = len(document)

        if page_count < 1:
            raise SourcePreparationError(
                "Your PDF contains no pages, so it cannot be used as an expense"
                " source. Your request will not be satisfied."
            )

        if page_count > MAX_PDF_PAGES:
            raise SourcePreparationError(
                f"Your PDF has {page_count} pages. Only PDFs with up to"
                f" {MAX_PDF_PAGES} pages are accepted, so your request will not be"
                " satisfied."
            )

        page_images: list[bytes] = []
        for index in range(page_count):
            page = document[index]
            bitmap = page.render(scale=_PDF_RENDER_SCALE)
            image = bitmap.to_pil()
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=_PDF_JPEG_QUALITY)
            page_images.append(buf.getvalue())

        logger.info("Rendered %s PDF page(s)", len(page_images))
        return ReceiptPagesSourceView(page_images=tuple(page_images))
