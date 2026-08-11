"""Pending Correction entity — tracks a user's in-progress Correction context.

This module has ZERO framework/IO imports — pure domain dataclass only.
"""

from __future__ import annotations

from dataclasses import dataclass

from expense_report.domain.models import ExtractionResult


@dataclass
class PendingCorrection:
    """Tracks a user's pending correction context after a partial extraction.

    Attributes:
        user_id: Telegram user ID.
        original_result: The partial extraction result being corrected.
        attempt_count: How many correction attempts have been made (starts at 1).
    """

    user_id: int
    original_result: ExtractionResult
    attempt_count: int = 1

    @property
    def maxed_out(self) -> bool:
        """True when the user has exhausted the maximum number of correction attempts."""
        return self.attempt_count >= 3
