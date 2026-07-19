"""Protocol compliance tests for ExtractionPort."""

from __future__ import annotations

from typing import Literal

from expense_report.domain.models import ExtractionResult
from expense_report.ports.extraction import ExtractionPort


class TestExtractionPortProtocol:
    """Verify that a class implementing ExtractionPort satisfies the protocol."""

    def test_protocol_compliance(self) -> None:
        """An object with an 'extract' method of the correct signature
        should be recognized as an ExtractionPort implementation."""

        class FakeExtractor:
            def extract(
                self,
                source: str | bytes,
                source_type: Literal["image", "text"],
            ) -> ExtractionResult:
                return ExtractionResult(
                    amount=None,
                    currency=None,
                    merchant=None,
                    date=None,
                    category=None,
                )

            def refine(
                self,
                original: ExtractionResult,
                correction_text: str,
            ) -> ExtractionResult:
                return ExtractionResult(
                    amount=None,
                    currency=None,
                    merchant=None,
                    date=None,
                    category=None,
                )

        extractor = FakeExtractor()
        assert isinstance(extractor, ExtractionPort), (
            "FakeExtractor must satisfy ExtractionPort protocol"
        )

    def test_protocol_returns_correct_type(self) -> None:
        """The protocol compliance check and actual call should both work."""

        class SimpleExtractor:
            def extract(
                self,
                source: str | bytes,
                source_type: Literal["image", "text"],
            ) -> ExtractionResult:
                return ExtractionResult(
                    amount=None,
                    currency=None,
                    merchant=None,
                    date=None,
                    category=None,
                )

            def refine(
                self,
                original: ExtractionResult,
                correction_text: str,
            ) -> ExtractionResult:
                return ExtractionResult(
                    amount=None,
                    currency=None,
                    merchant=None,
                    date=None,
                    category=None,
                )

        extractor = SimpleExtractor()
        result = extractor.extract("lunch 15 eur", "text")
        assert isinstance(result, ExtractionResult)
        assert result.is_complete is False
