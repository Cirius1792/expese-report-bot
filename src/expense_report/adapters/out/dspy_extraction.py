"""dSPy-based implementation of the ExtractionPort.

Uses an OpenAI-compatible LLM via dSPy for structured expense extraction
from receipt photos and free-text messages.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import dspy
from openai import OpenAI
from PIL import Image

from expense_report.domain.models import ExtractionResult

logger = logging.getLogger(__name__)


class ExpenseSignature(dspy.Signature):
    """Extract structured expense data from a free-text description."""

    source: str = dspy.InputField(desc="The free-text expense description (e.g., 'lunch 15 eur')")
    amount: str = dspy.OutputField(desc="The expense amount as a decimal number (e.g., 42.50)")
    currency: str = dspy.OutputField(desc="3-letter ISO 4217 currency code (e.g., EUR, USD, GBP)")
    merchant: str = dspy.OutputField(desc="The merchant or vendor name")
    date: str = dspy.OutputField(desc="The expense date in YYYY-MM-DD format")
    category: str | None = dspy.OutputField(
        desc="Optional expense category (e.g., food, transport, utilities)"
    )


class ExpenseImageSignature(dspy.Signature):
    """Extract structured expense data from a receipt image."""

    image_b64: str = dspy.InputField(
        desc="Base64-encoded JPEG image of the receipt",
        is_image=True,
    )
    amount: str = dspy.OutputField(desc="The expense amount as a decimal number (e.g., 42.50)")
    currency: str = dspy.OutputField(desc="3-letter ISO 4217 currency code (e.g., EUR, USD, GBP)")
    merchant: str = dspy.OutputField(desc="The merchant or vendor name")
    date: str = dspy.OutputField(desc="The expense date in YYYY-MM-DD format")
    category: str | None = dspy.OutputField(
        desc="Optional expense category (e.g., food, transport, utilities)"
    )


_ISO4217_RE = re.compile(r"^[A-Z]{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DspyExtractionAdapter:
    """Extraction adapter that uses dSPy with an OpenAI-compatible LLM.

    Reads LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL from environment variables.
    Uses ChainOfThought with a custom Signature for structured extraction.
    """

    def __init__(self) -> None:
        base_url = os.environ["LLM_BASE_URL"]
        api_key = os.environ["LLM_API_KEY"]
        model = os.environ["LLM_MODEL"]

        self._lm = dspy.LM(
            model=model,
            api_key=api_key,
            api_base=base_url,
            max_tokens=500,
            temperature=0.0,
        )
        dspy.configure(lm=self._lm)
        self._text_extractor = dspy.ChainOfThought(ExpenseSignature)
        self._image_extractor = dspy.Predict(ExpenseImageSignature)

    def refine(
        self,
        original: ExtractionResult,
        correction_text: str,
    ) -> ExtractionResult:
        """Refine a partial extraction with user-supplied corrections.

        Creates a combined prompt describing the original partial extraction
        and the user's correction text, then re-runs extraction via dSPy.
        """
        logger.info("Refining extraction with user correction text")
        source = (
            f"Original partial extraction:\n"
            f"  Amount: {original.amount}\n"
            f"  Currency: {original.currency}\n"
            f"  Merchant: {original.merchant}\n"
            f"  Date: {original.date}\n"
            f"  Category: {original.category}\n\n"
            f"User correction: {correction_text}"
        )
        result = self._call_refine(source)
        logger.info(
            "Refine complete: %s%s",
            result.amount or "?",
            result.currency or "",
        )
        return result

    def _call_refine(self, source: str) -> ExtractionResult:
        """Call the dSPy extractor with a combined source and return an ExtractionResult."""
        prediction = self._call_text_with_retry(source)
        return ExtractionResult(
            amount=self._parse_amount(prediction.amount),
            currency=self._parse_currency(prediction.currency),
            merchant=prediction.merchant if prediction.merchant else None,
            date=self._parse_date(prediction.date),
            category=prediction.category if prediction.category else None,
        )

    def extract(
        self,
        source: str | bytes,
        source_type: Literal["image", "text"],
    ) -> ExtractionResult:
        """Extract structured expense data from the given source."""
        if source_type == "image":
            assert isinstance(source, bytes), "Image source must be bytes"
            logger.info("Extracting from image source")
            image_b64 = self._image_to_base64(source)
            fields = self._call_image_with_retry(image_b64)
            result = ExtractionResult(
                amount=self._parse_amount(fields["amount"]),
                currency=self._parse_currency(fields["currency"]),
                merchant=fields["merchant"] if fields["merchant"] else None,
                date=self._parse_date(fields["date"]),
                category=fields["category"] if fields["category"] else None,
            )
            logger.info(
                "Image extraction complete: %s%s",
                result.amount or "?",
                result.currency or "",
            )
            return result
        else:
            assert isinstance(source, str), "Text source must be a string"
            logger.info("Extracting from text source")
            prediction = self._call_text_with_retry(source)
            result = ExtractionResult(
                amount=self._parse_amount(prediction.amount),
                currency=self._parse_currency(prediction.currency),
                merchant=prediction.merchant if prediction.merchant else None,
                date=self._parse_date(prediction.date),
                category=prediction.category if prediction.category else None,
            )
            logger.info(
                "Text extraction complete: %s%s",
                result.amount or "?",
                result.currency or "",
            )
            return result

    def _image_to_base64(self, image_bytes: bytes) -> str:
        """Convert image bytes to a resized base64 string for vision LLMs.

        Resizes to max 768px longest side to preserve receipt readability
        while staying within context limits. Returns raw base64 without data URL prefix.
        """
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((1536, 1536), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    def _call_text_with_retry(self, source: str) -> Any:
        """Call the text dSPy extractor with retry logic (3 total attempts)."""
        last_exception: Exception | None = None
        delays = [1, 2]
        for attempt in range(3):
            try:
                logger.debug("Text extraction attempt %s/3", attempt + 1)
                return self._text_extractor(source=source)
            except Exception as e:
                last_exception = e
                logger.warning(
                    "Text extraction failed (attempt %s/3): %s",
                    attempt + 1,
                    type(e).__name__,
                )
                if attempt < 2:
                    time.sleep(delays[attempt])
        logger.error(
            "Text extraction failed after 3 attempts: %s",
            type(last_exception).__name__,
        )
        raise last_exception  # type: ignore[misc]

    def _call_image_with_retry(self, image_b64: str) -> dict[str, str]:
        """Call the vision model directly via OpenAI-compatible API for image extraction.

        Uses direct API call instead of dSPy because dSPy's ChainOfThought prompt
        overhead exceeds the model's context window for vision tasks.
        """
        client = OpenAI(
            base_url=os.environ["LLM_BASE_URL"],
            api_key=os.environ["LLM_API_KEY"],
        )
        delays = [1, 2]
        last_exception: Exception | None = None

        for attempt in range(3):
            try:
                logger.debug("Image extraction attempt %s/3", attempt + 1)
                response = client.chat.completions.create(
                    model=os.environ["LLM_MODEL"].removeprefix("openai/"),
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract structured expense data from this receipt image. "
                                        "Return a JSON object with these fields:\n"
                                        "- amount: decimal number (e.g., 42.50)\n"
                                        "- currency: 3-letter ISO 4217 code (e.g., EUR, USD)\n"
                                        "- merchant: vendor name\n"
                                        "- date: YYYY-MM-DD format. Read every digit carefully.\n"
                                        "European receipts often use DD/MM/YYYY"
                                        " — convert to YYYY-MM-DD.\n"
                                        "- category: expense category"
                                        " (e.g., food, transport, hotel)"
                                    ),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=300,
                    temperature=0.0,
                )
                content = response.choices[0].message.content
                assert content is not None
                return self._parse_direct_response(content)
            except Exception as e:
                last_exception = e
                logger.warning(
                    "Image extraction failed (attempt %s/3): %s",
                    attempt + 1,
                    type(e).__name__,
                )
                if attempt < 2:
                    time.sleep(delays[attempt])
        logger.error(
            "Image extraction failed after 3 attempts: %s",
            type(last_exception).__name__,
        )
        raise last_exception  # type: ignore[misc]

    @staticmethod
    def _parse_direct_response(content: str) -> dict[str, str]:
        """Parse JSON from the direct API response into a dict of field values."""
        import json

        # Strip markdown code fences if present
        text = content.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        data = json.loads(text)
        # Handle nested "expense" key if present
        if "expense" in data and isinstance(data["expense"], dict):
            data = data["expense"]
        return {
            "amount": str(data.get("amount", "")),
            "currency": str(data.get("currency", "")),
            "merchant": str(data.get("merchant", "")),
            "date": str(data.get("date", "")),
            "category": str(data.get("category", "")),
        }

    @staticmethod
    def _parse_currency(value: str) -> str | None:
        """Validate and return ISO 4217 currency code, or None."""
        if not value or not _ISO4217_RE.match(value):
            return None
        return value

    @staticmethod
    def _parse_date(value: str) -> date | None:
        """Parse YYYY-MM-DD date string, or return None."""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_amount(value: str) -> Decimal | None:
        """Parse a decimal amount string, or return None."""
        if not value:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError):
            return None
