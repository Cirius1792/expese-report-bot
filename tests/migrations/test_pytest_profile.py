"""The default pytest profile is hermetic; integration is opt-in (ADR 0014)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]

INTEGRATION_TESTS = (
    "test_fresh_database_gets_schema_and_tracking_tables",
    "test_snapshot_matches_changelog",
)


def _collect(*args: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_default_profile_deselects_integration() -> None:
    """A plain `pytest` run must not collect the Docker-dependent tests."""
    collected = _collect()
    for test_name in INTEGRATION_TESTS:
        assert test_name not in collected


def test_integration_profile_selects_integration() -> None:
    """The integration profile collects the Docker-dependent tests."""
    collected = _collect("-o", "addopts=", "-m", "integration")
    for test_name in INTEGRATION_TESTS:
        assert test_name in collected
