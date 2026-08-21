"""Tests for SourcePreparationAdapter (adapters/out/source_preparation.py).

Sociable unit tests: the real pypdfium2 renderer is exercised against
in-memory PDFs generated with Pillow (no binary fixtures). Only the
zero-page document case mocks the PDFium document boundary because a
valid 0-page PDF cannot be produced by Pillow.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from expense_report.domain.source_types import SourceType
from expense_report.ports.source_preparation import (
    FreeTextSourceView,
    ReceiptPagesSourceView,
    SourcePreparationError,
    SourcePreparationPort,
)


def _make_pdf(num_pages: int, page_size: tuple[int, int] = (100, 140)) -> bytes:
    """Generate an in-memory multi-page PDF with Pillow.

    Each page is a distinct solid color so page order can be verified
    after rendering: red channel = (page_index * 60) % 256.
    """
    buf = BytesIO()
    pages = [
        Image.new("RGB", page_size, color=((page_index * 60) % 256, 30, 30))
        for page_index in range(num_pages)
    ]
    pages[0].save(buf, "PDF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


class TestTextPreparation:
    """TEXT source type normalizes to a FreeTextSourceView."""

    def test_text_returns_free_text_view(self) -> None:
        """Free text is wrapped verbatim in a FreeTextSourceView."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        view = adapter.prepare("lunch 15 eur", SourceType.TEXT)

        assert view == FreeTextSourceView(text="lunch 15 eur")

    def test_text_with_non_string_raises(self) -> None:
        """Passing bytes as a TEXT source is rejected."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        with pytest.raises(AssertionError):
            adapter.prepare(b"not text", SourceType.TEXT)


class TestImagePreparation:
    """IMAGE source type normalizes to a single-page ReceiptPagesSourceView."""

    def test_image_returns_single_page_view_with_original_bytes(self) -> None:
        """The raw image bytes pass through untouched (no decode, no resize)."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        raw = b"\x89PNG-fake-image-bytes"

        view = adapter.prepare(raw, SourceType.IMAGE)

        assert isinstance(view, ReceiptPagesSourceView)
        assert view.page_images == (raw,)

    def test_image_with_non_bytes_raises(self) -> None:
        """Passing str as an IMAGE source is rejected."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        with pytest.raises(AssertionError):
            adapter.prepare("not bytes", SourceType.IMAGE)


class TestPdfPreparation:
    """PDF source type renders ordered page images via pypdfium2."""

    def test_pdf_one_page_renders_single_jpeg_image(self) -> None:
        """A 1-page PDF produces exactly one JPEG page image."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        view = adapter.prepare(_make_pdf(1), SourceType.PDF)

        assert isinstance(view, ReceiptPagesSourceView)
        assert len(view.page_images) == 1
        assert view.page_images[0].startswith(b"\xff\xd8")  # JPEG SOI marker

    def test_pdf_five_pages_accepted_and_renders_five_images(self) -> None:
        """Boundary: a 5-page PDF is accepted and renders exactly 5 page images."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        view = adapter.prepare(_make_pdf(5), SourceType.PDF)

        assert isinstance(view, ReceiptPagesSourceView)
        assert len(view.page_images) == 5

    def test_pdf_renders_at_scale_two(self) -> None:
        """Rendering uses pypdfium2 scale=2 (output is 2x the page size)."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        view = adapter.prepare(_make_pdf(1, page_size=(100, 140)), SourceType.PDF)

        assert isinstance(view, ReceiptPagesSourceView)
        rendered = Image.open(BytesIO(view.page_images[0]))
        assert rendered.size == (200, 280)

    def test_pdf_renders_jpeg_quality_92(self) -> None:
        """Each page is encoded as JPEG with quality=92."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        real_save = Image.Image.save
        jpeg_calls: list[dict[str, object]] = []

        def recording_save(
            self: Image.Image,
            fp: object,
            format: str | None = None,
            **params: object,
        ) -> None:
            if format == "JPEG":
                jpeg_calls.append(params)
            real_save(self, fp, format=format, **params)

        pdf_bytes = _make_pdf(1)
        with patch.object(Image.Image, "save", recording_save):
            adapter = SourcePreparationAdapter()
            adapter.prepare(pdf_bytes, SourceType.PDF)

        assert jpeg_calls, "Expected at least one JPEG save during rendering"
        for params in jpeg_calls:
            assert params.get("quality") == 92

    def test_pdf_preserves_page_order(self) -> None:
        """Rendered page images keep PDF page order (no reorder, no drop)."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        view = adapter.prepare(_make_pdf(4), SourceType.PDF)

        assert isinstance(view, ReceiptPagesSourceView)
        assert len(view.page_images) == 4
        for index, page_bytes in enumerate(view.page_images):
            rendered = Image.open(BytesIO(page_bytes)).convert("RGB")
            expected_red = (index * 60) % 256
            actual_red = rendered.getpixel((5, 5))[0]
            assert abs(actual_red - expected_red) <= 8, (
                f"page {index} rendered out of order: expected red≈{expected_red}, got {actual_red}"
            )

    def test_pdf_six_pages_rejected_naming_count_and_limit(self) -> None:
        """A 6-page PDF is rejected with the page count and the 5-page limit."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        with pytest.raises(SourcePreparationError) as excinfo:
            adapter.prepare(_make_pdf(6), SourceType.PDF)

        message = str(excinfo.value)
        assert "6" in message
        assert "5" in message

    def test_pdf_zero_pages_rejected(self) -> None:
        """A 0-page PDF document is rejected via SourcePreparationError."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        with patch(
            "expense_report.adapters.out.source_preparation.pdfium.PdfDocument"
        ) as mock_document_cls:
            fake_document = MagicMock()
            fake_document.__len__.return_value = 0
            mock_document_cls.return_value = fake_document

            adapter = SourcePreparationAdapter()
            with pytest.raises(SourcePreparationError):
                adapter.prepare(b"%PDF-1.4 fake", SourceType.PDF)

    def test_invalid_pdf_bytes_rejected(self) -> None:
        """Invalid/corrupt PDF bytes are rejected via SourcePreparationError."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        with pytest.raises(SourcePreparationError):
            adapter.prepare(b"this is definitely not a pdf", SourceType.PDF)

    def test_pdf_with_non_bytes_raises(self) -> None:
        """Passing str as a PDF source is rejected."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        adapter = SourcePreparationAdapter()
        with pytest.raises(AssertionError):
            adapter.prepare("not bytes", SourceType.PDF)


class TestPortCompliance:
    """The adapter satisfies the SourcePreparationPort protocol."""

    def test_adapter_satisfies_source_preparation_port(self) -> None:
        """SourcePreparationAdapter is recognized as a SourcePreparationPort."""
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )

        assert isinstance(SourcePreparationAdapter(), SourcePreparationPort)
