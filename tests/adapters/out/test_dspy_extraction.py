"""Tests for DspyExtractionAdapter."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from expense_report.domain.models import ExtractionResult
from expense_report.ports.extraction import ExtractionPort


class TestConstructor:
    """Verify adapter initializes dSPy correctly from env vars."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key-123",
            "LLM_MODEL": "test-model/v1",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    @patch("dspy.ChainOfThought")
    @patch("dspy.Predict")
    def test_initializes_dspy_lm_with_correct_env_vars(
        self,
        mock_predict_cls: MagicMock,
        mock_chain: MagicMock,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Constructor reads env vars and configures dSPy LM."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_text_predictor = MagicMock()
        mock_image_predictor = MagicMock()
        mock_chain.return_value = mock_text_predictor
        mock_predict_cls.return_value = mock_image_predictor

        # Import after patching
        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        adapter = DspyExtractionAdapter()

        mock_lm_cls.assert_called_once_with(
            model="test-model/v1",
            api_key="test-key-123",
            api_base="http://test:8080",
            max_tokens=500,
            temperature=0.0,
        )
        mock_configure.assert_called_once_with(lm=mock_lm)
        mock_chain.assert_called_once()  # text ChainOfThought
        mock_predict_cls.assert_called_once()  # image Predict
        assert adapter._text_extractor is mock_text_predictor
        assert adapter._image_extractor is mock_image_predictor

    def test_requires_env_vars(self) -> None:
        """Constructor raises KeyError when env vars are missing."""
        with patch.dict(os.environ, {}, clear=True):
            from expense_report.adapters.out.dspy_extraction import (
                DspyExtractionAdapter,
            )

            with pytest.raises(KeyError):
                DspyExtractionAdapter()


class TestExtractText:
    """Extract from text source."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_extract_text_returns_extraction_result(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Extracting from text returns an ExtractionResult with parsed fields."""
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
            result = adapter.extract("supermarket 42.50 eur", "text")

        assert isinstance(result, ExtractionResult)
        assert result.amount == Decimal("42.50")
        assert result.currency == "EUR"
        assert result.merchant == "Supermarket"
        assert result.date == date(2026, 7, 15)
        assert result.category == "groceries"
        assert result.is_complete is True

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_satisfies_extraction_port(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """DspyExtractionAdapter is recognized as an ExtractionPort."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "USD"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()

        assert isinstance(adapter, ExtractionPort)


class TestExtractImage:
    """Extract from image bytes."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    @patch("PIL.Image.open")
    @patch("expense_report.adapters.out.dspy_extraction.OpenAI")
    def test_extract_image_uses_openai_vision_api(
        self,
        mock_openai_cls: MagicMock,
        mock_image_open: MagicMock,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Image extraction uses OpenAI vision API with image_url content part."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        # Mock PIL image operations
        mock_img = MagicMock()
        mock_image_open.return_value = mock_img
        def fake_save(buf, format, quality):
            buf.write(b"fake-jpeg-data")
        mock_img.save.side_effect = fake_save

        # Mock OpenAI client response
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"amount":"15.00","currency":"EUR","merchant":"Cafe","date":"2026-07-10","category":"food"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch("dspy.ChainOfThought"), patch("dspy.Predict"):
            adapter = DspyExtractionAdapter()
            image_bytes = b"fake-image-data"
            result = adapter.extract(image_bytes, "image")

        # Verify OpenAI client was called with image_url content
        create_call = mock_client.chat.completions.create
        assert create_call.called
        messages = create_call.call_args[1]["messages"]
        content_parts = messages[0]["content"]
        assert content_parts[0]["type"] == "text"
        assert content_parts[1]["type"] == "image_url"
        assert content_parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

        assert isinstance(result, ExtractionResult)
        assert result.amount == Decimal("15.00")

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_extract_image_invalid_type_raises(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Passing str as image raises AssertionError."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch("dspy.ChainOfThought", return_value=MagicMock()):
            adapter = DspyExtractionAdapter()

        with pytest.raises(AssertionError):
            adapter.extract("not bytes", "image")  # type: ignore[arg-type]


class TestRetry:
    """Retry logic on LLM failures."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_retry_succeeds_on_second_attempt(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """After one failure, retry succeeds on the second attempt."""
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

        with patch("dspy.ChainOfThought", return_value=mock_predictor):
            with patch("time.sleep") as mock_sleep:
                adapter = DspyExtractionAdapter()
                result = adapter.extract("20 usd store", "text")

        assert call_count == 2
        mock_sleep.assert_called_once_with(1)
        assert result.amount == Decimal("20.00")

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_retry_exhausts_all_attempts(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """All 3 attempts fail and the last exception is re-raised."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_predictor = MagicMock(
            side_effect=RuntimeError("LLM consistently failing")
        )

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch("dspy.ChainOfThought", return_value=mock_predictor):
            with patch("time.sleep") as mock_sleep:
                adapter = DspyExtractionAdapter()

                with pytest.raises(RuntimeError, match="consistently failing"):
                    adapter.extract("test text", "text")

        assert mock_predictor.call_count == 3
        assert mock_sleep.call_args_list[0][0][0] == 1  # first sleep 1s
        assert mock_sleep.call_args_list[1][0][0] == 2  # second sleep 2s


class TestValidation:
    """Field validation and sanitization."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_invalid_currency_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Non-ISO-4217 currency codes are replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "INVALID"  # Not 3 uppercase letters
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 shop", "text")

        assert result.currency is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_lowercase_currency_rejected(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Lowercase currency codes are rejected (not 3 uppercase letters)."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "eur"  # lowercase
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 shop", "text")

        assert result.currency is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_unparseable_date_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Dates not in YYYY-MM-DD format are replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "not-a-date"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur shop", "text")

        assert result.date is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_empty_date_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Empty strings for date are replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = ""
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur shop", "text")

        assert result.date is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_unparseable_amount_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Amounts that cannot be parsed as Decimal are replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "not-a-number"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur shop", "text")

        assert result.amount is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_empty_amount_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Empty amount string is replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = ""
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur shop", "text")

        assert result.amount is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_empty_merchant_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Empty merchant string is replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = ""
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur", "text")

        assert result.merchant is None

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_empty_category_set_to_none(
        self,
        mock_configure: MagicMock,
        mock_lm_cls: MagicMock,
    ) -> None:
        """Empty category string is replaced with None."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm

        mock_prediction = MagicMock()
        mock_prediction.amount = "10.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Shop"
        mock_prediction.date = "2026-07-01"
        mock_prediction.category = ""

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()
            result = adapter.extract("10 eur shop", "text")

        assert result.category is None


class TestRefine:
    """Tests for the refine method (correction flow)."""

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_returns_extraction_result(
        self, mock_configure: MagicMock, mock_lm_cls: MagicMock
    ) -> None:
        """Refine returns an ExtractionResult instance."""
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
        result = adapter.refine(original, "Supermarket, 2026-07-15, EUR")
        assert isinstance(result, ExtractionResult)

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_fills_missing_fields(
        self, mock_configure: MagicMock, mock_lm_cls: MagicMock
    ) -> None:
        """Refine fills in missing fields based on correction text."""
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
        result = adapter.refine(original, "it was at Supermarket, EUR, 2026-07-15")
        assert result.currency == "EUR"
        assert result.merchant == "Supermarket"
        assert result.date == date(2026, 7, 15)
        assert result.is_complete is True

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_preserves_existing_fields(
        self, mock_configure: MagicMock, mock_lm_cls: MagicMock
    ) -> None:
        """Refine preserves original fields even when correction doesn't mention them."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_prediction = MagicMock()
        mock_prediction.amount = "15.00"
        mock_prediction.currency = "EUR"
        mock_prediction.merchant = "Cafe"
        mock_prediction.date = "2026-07-20"
        mock_prediction.category = "food"

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with patch(
            "dspy.ChainOfThought",
            return_value=MagicMock(return_value=mock_prediction),
        ):
            adapter = DspyExtractionAdapter()

        original = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant=None,
            date=None,
            category="food",
        )
        result = adapter.refine(original, "Cafe on 2026-07-20")
        # Existing fields preserved
        assert result.amount == Decimal("15.00")
        assert result.currency == "EUR"
        assert result.category == "food"
        # New fields filled
        assert result.merchant == "Cafe"
        assert result.date == date(2026, 7, 20)
        assert result.is_complete is True

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_retries_on_llm_failure(
        self, mock_configure: MagicMock, mock_lm_cls: MagicMock
    ) -> None:
        """Refine retries on LLM failure and succeeds on second attempt."""
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
            patch("time.sleep") as mock_sleep,
        ):
            adapter = DspyExtractionAdapter()

            original = ExtractionResult(
                amount=None,
                currency=None,
                merchant=None,
                date=None,
                category=None,
            )
            result = adapter.refine(original, "20 usd store")

        assert call_count == 2
        mock_sleep.assert_called_once_with(1)
        assert result.amount == Decimal("20.00")
        assert result.merchant == "Store"

    @patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://test:8080",
            "LLM_API_KEY": "test-key",
            "LLM_MODEL": "test-model",
        },
        clear=True,
    )
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_refine_exhausts_retries(
        self, mock_configure: MagicMock, mock_lm_cls: MagicMock
    ) -> None:
        """Refine raises after all retry attempts exhausted."""
        mock_lm = MagicMock()
        mock_lm_cls.return_value = mock_lm
        mock_predictor = MagicMock(
            side_effect=RuntimeError("LLM consistently failing")
        )

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        with (
            patch("dspy.ChainOfThought", return_value=mock_predictor),
            patch("time.sleep") as mock_sleep,
        ):
            adapter = DspyExtractionAdapter()

            original = ExtractionResult(
                amount=None,
                currency=None,
                merchant=None,
                date=None,
                category=None,
            )
            with pytest.raises(RuntimeError, match="consistently failing"):
                adapter.refine(original, "test correction")

        assert mock_predictor.call_count == 3
        assert mock_sleep.call_args_list[0][0][0] == 1
        assert mock_sleep.call_args_list[1][0][0] == 2

