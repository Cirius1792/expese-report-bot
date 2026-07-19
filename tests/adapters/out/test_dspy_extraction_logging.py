"""Tests for operational logging in DspyExtractionAdapter.

Verifies that extraction, refine, and retry operations produce appropriate
log messages without leaking payloads or secrets.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from expense_report.domain.models import ExtractionResult


@pytest.fixture(autouse=True)
def _setup_logging() -> None:
    """Ensure root logger is configured for caplog tests."""
    logging.basicConfig(level=logging.DEBUG, force=True)


@pytest.fixture
def env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set required env vars for adapter construction."""
    monkeypatch.setenv("LLM_BASE_URL", "http://test:8080")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")


class TestTextExtractionLogging:
    """Verify text extraction produces operational logs."""

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_extract_text_logs_info(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Text extraction logs at INFO level."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_prediction = MagicMock()
        mock_prediction.amount = "42.50"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-15"
        mock_prediction.category = "food"

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.INFO)
        result = adapter.extract("lunch 15 eur", "text")

        assert result.is_complete is True
        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "extract" in messages.lower() or "text" in messages.lower(), (
            f"No extraction-related INFO log found. Captured: {[r.message for r in records]}"
        )

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_extract_text_does_not_log_payload(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Text extraction does not log the full source text."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_prediction = MagicMock()
        mock_prediction.amount = "42.50"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-15"
        mock_prediction.category = "food"

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.DEBUG)

        source_text = "this is a very specific expense description that should not appear in logs"
        adapter.extract(source_text, "text")

        for record in caplog.records:
            assert source_text not in record.message, (
                f"Source text leaked in log message: {record.message}"
            )
            assert "Shop" not in record.message, (
                f"Extracted merchant leaked in log message: {record.message}"
            )


class TestImageExtractionLogging:
    """Verify image extraction produces operational logs."""

    @patch("dspy.LM")
    @patch("dspy.configure")
    @patch("PIL.Image.open")
    @patch("expense_report.adapters.out.dspy_extraction.OpenAI")
    def test_extract_image_logs_info(
        self,
        mock_openai_cls: MagicMock,
        mock_image_open: MagicMock,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Image extraction logs at INFO level."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_img = MagicMock()
        mock_image_open.return_value = mock_img

        def fake_save(buf, format, quality):
            buf.write(b"fake-jpeg-data")

        mock_img.save.side_effect = fake_save

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"amount":"15.00","currency":"EUR","merchant":"Cafe","date":"2026-07-10","category":"food"}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch("dspy.ChainOfThought"), patch("dspy.Predict"):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.INFO)
        result = adapter.extract(b"fake-image-data", "image")

        assert result.is_complete is True
        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "image" in messages.lower() or "extract" in messages.lower(), (
            f"No image/extraction-related INFO log found. Captured: {[r.message for r in records]}"
        )

    @patch("dspy.LM")
    @patch("dspy.configure")
    @patch("PIL.Image.open")
    @patch("expense_report.adapters.out.dspy_extraction.OpenAI")
    def test_extract_image_does_not_log_base64(
        self,
        mock_openai_cls: MagicMock,
        mock_image_open: MagicMock,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Image extraction does not log base64 payloads."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_img = MagicMock()
        mock_image_open.return_value = mock_img

        def fake_save(buf, format, quality):
            buf.write(b"fake-jpeg-data")

        mock_img.save.side_effect = fake_save

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"amount":"15.00","currency":"EUR","merchant":"Cafe","date":"2026-07-10","category":"food"}'
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch("dspy.ChainOfThought"), patch("dspy.Predict"):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.DEBUG)
        adapter.extract(b"fake-image-data", "image")

        for record in caplog.records:
            assert "base64" not in record.message.lower(), (
                f"Log message contains 'base64': {record.message}"
            )
            assert "ZmFrZS1qcGVn" not in record.message, (
                f"Base64 payload fragment leaked in log message: {record.message}"
            )
            assert "Cafe" not in record.message, (
                f"Extracted merchant leaked in log message: {record.message}"
            )
            # Check for typical base64 character patterns (long sequences of alphanumeric)
            assert len(record.message) < 1000, (
                f"Log message suspiciously long: {len(record.message)} chars"
            )


class TestRefineLogging:
    """Verify refine operations produce operational logs."""

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_logs_info(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Refine logs at INFO level."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_prediction = MagicMock()
        mock_prediction.amount = "42.50"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Supermarket"
        mock_prediction.date = "2026-07-15"
        mock_prediction.category = "groceries"

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()

        original = ExtractionResult(
            amount=Decimal("42.50"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )

        caplog.set_level(logging.INFO)
        adapter.refine(original, "Supermarket, EUR")

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        all_messages = " ".join(r.message for r in caplog.records)
        assert (
            "refine" in messages.lower()
            or "correction" in messages.lower()
            or "extract" in messages.lower()
        ), f"No refine-related INFO log found. Captured: {[r.message for r in records]}"
        assert "Supermarket" not in all_messages


class TestRetryLogging:
    """Verify retry attempts produce appropriate log messages."""

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_retry_attempt_logs_warning(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Retry attempt on LLM failure logs at WARNING level."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_prediction = MagicMock()
        mock_prediction.amount = "20.00"
        mock_prediction.currency = "USD"
        mock_prediction.merchant = "Store"
        mock_prediction.date = "2026-07-05"
        mock_prediction.category = ""

        call_count = 0

        def side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("LLM unreachable")
            return mock_prediction

        mock_predictor = MagicMock(side_effect=side_effect)

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with (
            patch("dspy.ChainOfThought", return_value=mock_predictor),
            patch("time.sleep"),
        ):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.WARNING)
        adapter.extract("20 usd store", "text")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) >= 1, (
            f"No WARNING log for retry found. Captured: {[r.message for r in caplog.records]}"
        )
        # Should mention the exception type (ConnectionError)
        messages = " ".join(r.message for r in warning_records)
        assert "ConnectionError" in messages or "connection" in messages.lower()

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_retry_does_not_log_api_key(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Retry logs do not contain the LLM_API_KEY."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_predictor = MagicMock(side_effect=RuntimeError("fail"))

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with (
            patch("dspy.ChainOfThought", return_value=mock_predictor),
            patch("time.sleep"),
        ):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.DEBUG)
        with pytest.raises(RuntimeError):
            adapter.extract("test", "text")

        for record in caplog.records:
            assert "test-key" not in record.message, (
                f"API key leaked in log message: {record.message}"
            )
            assert "LLM_API_KEY" not in record.message.upper()

    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_retry_does_not_log_source_text(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
        env_setup: None,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Retry logs do not contain the full source text."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_predictor = MagicMock(side_effect=RuntimeError("fail"))

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with (
            patch("dspy.ChainOfThought", return_value=mock_predictor),
            patch("time.sleep"),
        ):
            adapter = DspyExtractionAdapter()

        caplog.set_level(logging.DEBUG)
        source = "my secret lunch at fancy restaurant cost 42.50 euros"
        with pytest.raises(RuntimeError):
            adapter.extract(source, "text")

        for record in caplog.records:
            assert source not in record.message, (
                f"Source text leaked in log message: {record.message}"
            )
