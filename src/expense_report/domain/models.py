"""Domain entities and value objects for expense reports.

This module MUST have zero framework/IO imports — frozen dataclasses only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Expense:
    """A structured record of money spent, extracted from a Receipt."""

    id: int | None
    amount: Decimal
    currency: str
    merchant: str
    date: date
    category: str | None
    user_id: int
    receipt_photo_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class ExtractionResult:
    """Structured output from LLM extraction of a Receipt or free-text message.

    Mandatory fields: amount, currency, merchant, date.
    Category is optional.
    """

    amount: Decimal | None
    currency: str | None
    merchant: str | None
    date: date | None
    category: str | None

    @property
    def is_complete(self) -> bool:
        """True when all mandatory fields (amount, currency, merchant, date) are present.

        Category is optional, so it does not affect completeness.
        """
        return (
            self.amount is not None
            and self.currency is not None
            and self.merchant is not None
            and self.date is not None
        )
