"""Correction state management — store owned by the application workflow.

The store is transient, in-process session state and is NOT persisted.
"""

from __future__ import annotations

from expense_report.domain.correction_state import PendingCorrection


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
