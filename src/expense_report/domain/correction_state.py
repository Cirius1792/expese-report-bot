"""Correction state management for the correction flow.

Tracks pending user corrections after partial extractions.
This module has ZERO framework/IO imports — pure domain classes only.
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


class CorrectionStore:
    """In-memory store for active correction sessions.

    This is transient session state and is NOT persisted to any database.
    """

    # TODO: if we ever need to deploy multiple instances of the bot, we will need to persist this

    def __init__(self) -> None:
        self._store: dict[int, PendingCorrection] = {}

    def set(self, user_id: int, correction: PendingCorrection) -> None:
        """Store a pending correction for the given user.

        Overwrites any existing pending correction for the same user.
        """
        self._store[user_id] = correction

    def get(self, user_id: int) -> PendingCorrection | None:
        """Retrieve the pending correction for a user, or None if none exists."""
        return self._store.get(user_id)

    def remove(self, user_id: int) -> None:
        """Remove the pending correction for a user, if one exists."""
        self._store.pop(user_id, None)
