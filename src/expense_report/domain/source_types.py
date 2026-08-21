"""Source type enum for expense recording.

Plain domain value object — zero framework/IO imports.
"""

from __future__ import annotations

from enum import Enum


class SourceType(Enum):
    """Kind of raw source a user provides for an expense."""

    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"
