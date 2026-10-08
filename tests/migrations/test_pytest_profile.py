"""The default pytest profile is hermetic; integration is opt-in (ADR 0014)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]

# Every Docker-dependent test, named explicitly: losing one marker must fail here.
EXPECTED_INTEGRATION: frozenset[str] = frozenset(
    {
        "tests/migrations/test_changelog.py::test_fresh_database_gets_schema_and_tracking_tables",
        "tests/migrations/test_changelog.py::test_reapplying_changelog_is_no_op",
        "tests/migrations/test_changelog.py::test_legacy_database_gains_deleted_at_without_losing_rows",
        "tests/migrations/test_changelog.py::test_current_schema_database_is_baselined_without_data_loss",
        "tests/migrations/test_schema_snapshot.py::test_snapshot_matches_changelog",
    }
)


def _collect(*args: str) -> set[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return {
        line.strip()
        for line in result.stdout.splitlines()
        if line.startswith("tests/") and "::" in line
    }


def test_default_profile_deselects_integration() -> None:
    """A plain `pytest` run must not collect any Docker-dependent test."""
    assert _collect() & EXPECTED_INTEGRATION == set()


def test_integration_profile_selects_exactly_the_expected_tests() -> None:
    """The integration profile collects every Docker-dependent test, and nothing else."""
    assert _collect("-o", "addopts=", "-m", "integration") == EXPECTED_INTEGRATION
