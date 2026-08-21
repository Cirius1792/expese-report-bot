"""Protocol compliance tests for SourcePreparationPort and the SourceView DTOs."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from expense_report.domain.source_types import SourceType
from expense_report.ports.source_preparation import (
    FreeTextSourceView,
    ReceiptPagesSourceView,
    SourcePreparationError,
    SourcePreparationPort,
    SourceView,
)


class TestSourcePreparationPortProtocol:
    """Verify that a class implementing SourcePreparationPort satisfies the protocol."""

    def test_protocol_compliance(self) -> None:
        """An object with a 'prepare' method of the correct signature is a SourcePreparationPort."""

        class FakePreparer:
            def prepare(self, source: str | bytes, source_type: SourceType) -> SourceView:
                if source_type is SourceType.TEXT:
                    assert isinstance(source, str)
                    return FreeTextSourceView(text=source)
                assert isinstance(source, bytes)
                return ReceiptPagesSourceView(page_images=(source,))

        assert isinstance(FakePreparer(), SourcePreparationPort)

    def test_protocol_returns_correct_types(self) -> None:
        """prepare returns the correct SourceView variant per SourceType."""

        class FakePreparer:
            def prepare(self, source: str | bytes, source_type: SourceType) -> SourceView:
                if source_type is SourceType.TEXT:
                    assert isinstance(source, str)
                    return FreeTextSourceView(text=source)
                assert isinstance(source, bytes)
                return ReceiptPagesSourceView(page_images=(source,))

        preparer = FakePreparer()
        assert preparer.prepare("lunch 15 eur", SourceType.TEXT) == FreeTextSourceView(
            text="lunch 15 eur"
        )
        assert preparer.prepare(b"bytes", SourceType.IMAGE) == ReceiptPagesSourceView(
            page_images=(b"bytes",)
        )


class TestFreeTextSourceView:
    """FreeTextSourceView is a frozen dataclass carrying plain text."""

    def test_carries_text(self) -> None:
        """The view stores the free-text source verbatim."""
        view = FreeTextSourceView(text="lunch 15 eur")
        assert view.text == "lunch 15 eur"

    def test_is_frozen(self) -> None:
        """The view is immutable."""
        view = FreeTextSourceView(text="x")
        with pytest.raises(FrozenInstanceError):
            view.text = "y"  # type: ignore


class TestReceiptPagesSourceView:
    """ReceiptPagesSourceView is a frozen dataclass carrying raw page-image bytes."""

    def test_carries_page_images_tuple(self) -> None:
        """The view stores an ordered tuple of raw page-image byte strings."""
        view = ReceiptPagesSourceView(page_images=(b"page-1", b"page-2"))
        assert view.page_images == (b"page-1", b"page-2")

    def test_is_frozen(self) -> None:
        """The view is immutable."""
        view = ReceiptPagesSourceView(page_images=(b"x",))
        with pytest.raises(FrozenInstanceError):
            view.page_images = (b"y",)  # type: ignore


class TestSourceViewUnion:
    """SourceView is exactly the union of the two normalized views."""

    def test_free_text_view_is_a_source_view(self) -> None:
        """FreeTextSourceView satisfies the SourceView union."""
        view: SourceView = FreeTextSourceView(text="lunch 15 eur")
        assert isinstance(view, FreeTextSourceView)

    def test_receipt_pages_view_is_a_source_view(self) -> None:
        """ReceiptPagesSourceView satisfies the SourceView union."""
        view: SourceView = ReceiptPagesSourceView(page_images=(b"page",))
        assert isinstance(view, ReceiptPagesSourceView)


class TestSourcePreparationError:
    """SourcePreparationError carries a user-facing message."""

    def test_carries_message(self) -> None:
        """The exception exposes the user-facing message via .message and str()."""
        error = SourcePreparationError("Your PDF has 8 pages. Your request will not be satisfied.")
        assert error.message == "Your PDF has 8 pages. Your request will not be satisfied."
        assert str(error) == "Your PDF has 8 pages. Your request will not be satisfied."
