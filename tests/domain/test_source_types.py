"""Tests for the SourceType enum (domain/source_types.py).

The enum is a plain domain value object: zero framework/IO imports.
"""

from __future__ import annotations

from enum import Enum

from expense_report.domain.source_types import SourceType


class TestSourceType:
    """Verify the SourceType enum shape and values."""

    def test_is_an_enum(self) -> None:
        """SourceType is a subclass of Enum."""
        assert issubclass(SourceType, Enum)

    def test_has_exactly_text_image_pdf_members(self) -> None:
        """SourceType exposes TEXT, IMAGE, and PDF members only."""
        assert {member.name for member in SourceType} == {"TEXT", "IMAGE", "PDF"}

    def test_text_value(self) -> None:
        """TEXT serializes as 'text'."""
        assert SourceType.TEXT.value == "text"

    def test_image_value(self) -> None:
        """IMAGE serializes as 'image'."""
        assert SourceType.IMAGE.value == "image"

    def test_pdf_value(self) -> None:
        """PDF serializes as 'pdf'."""
        assert SourceType.PDF.value == "pdf"
