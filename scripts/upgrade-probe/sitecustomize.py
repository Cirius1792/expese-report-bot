"""Stub the ``dspy`` module for the v0.7.0 -> PR upgrade probe.

Loaded by Python's ``site`` machinery (via ``PYTHONPATH``) *before* the real
``expense-extract`` CLI imports anything, so the released v0.7.0 image's CLI,
use case and repository run unchanged while the LLM boundary returns a fixed
prediction from ``STUB_*`` environment variables.

This mirrors the boundary mock already used by the BDD harness
(``features/environment.py``); it deliberately avoids a fake HTTP LLM server,
whose expected response format is dspy-version-sensitive.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock

_STUB_FIELDS = ("amount", "currency", "merchant", "date", "category")
_STUB_DEFAULTS = {
    "amount": "12.50",
    "currency": "EUR",
    "merchant": "Legacy Cafe",
    "date": "2026-01-02",
    "category": "food",
}


class _StaticPrediction:
    """A prediction object with the output fields the adapter reads."""

    def __init__(self) -> None:
        for field in _STUB_FIELDS:
            setattr(self, field, os.environ.get(f"STUB_{field.upper()}", _STUB_DEFAULTS[field]))
        self.reasoning = "stubbed prediction"


class _StaticChainOfThought:
    """Stand-in for ``dspy.ChainOfThought`` returning a fixed prediction."""

    def __init__(self, signature_class: Any) -> None:
        self._signature_class = signature_class

    def __call__(self, **_kwargs: Any) -> _StaticPrediction:
        return _StaticPrediction()


class _StaticPredict(_StaticChainOfThought):
    """Stand-in for ``dspy.Predict`` (vision path; unused by text probes)."""


def _install() -> None:
    dspy = MagicMock()
    dspy.Signature = type("Signature", (), {})
    dspy.InputField = MagicMock()
    dspy.OutputField = MagicMock()
    dspy.LM = MagicMock()
    dspy.configure = MagicMock()
    dspy.ChainOfThought = _StaticChainOfThought
    dspy.Predict = _StaticPredict
    sys.modules["dspy"] = dspy
    sys.modules["dspy.dspy"] = MagicMock()


_install()
