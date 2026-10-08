"""The committed schema snapshot must equal the changelog's output (ADR 0014)."""

from __future__ import annotations

import pytest

from tests._schema import SNAPSHOT_PATH, render_snapshot


@pytest.mark.integration
def test_snapshot_matches_changelog() -> None:
    assert SNAPSHOT_PATH.read_text(encoding="utf-8") == render_snapshot()
