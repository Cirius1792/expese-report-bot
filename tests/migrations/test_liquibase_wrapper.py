"""Hermetic tests for ``scripts/liquibase`` argument handling (no Docker needed).

The real wrapper is exercised end-to-end by the integration tests
(``tests/migrations/test_changelog.py``). These tests stub ``docker`` on
``PATH`` so the wrapper's own logic — argument parsing, staging, exit-code
propagation — is covered without pulling the Liquibase image.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
WRAPPER = REPO_ROOT / "scripts" / "liquibase"
CHANGELOG = "db/changelog/db.changelog.xml"


def _run_wrapper(
    tmp_path: Path, *args: str, docker_rc: int = 0
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run the wrapper with a fake ``docker`` that records its arguments."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "docker-args"
    fake = bindir / "docker"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\nexit {docker_rc}\n')
    fake.chmod(0o755)
    result = subprocess.run(
        [str(WRAPPER), *args],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "LIQUIBASE_SHIM_DIR": str(tmp_path / "stage"),
            "LIQUIBASE_REPO_ROOT": str(REPO_ROOT),
        },
    )
    lines = log.read_text().splitlines() if log.exists() else []
    return result, lines


def _db(tmp_path: Path, name: str = "expenses.db") -> Path:
    db = tmp_path / name
    db.write_bytes(b"")
    return db


def test_wrapper_forwards_caller_changelog(tmp_path: Path) -> None:
    db = _db(tmp_path)
    result, args = _run_wrapper(
        tmp_path,
        "update",
        f"--url=jdbc:sqlite:{db}",
        "--changelog-file=db/changelog/custom.xml",
    )
    assert result.returncode == 0
    assert "LIQUIBASE_CHANGELOG=db/changelog/custom.xml" in args


def test_wrapper_defaults_changelog_to_repo_value(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, args = _run_wrapper(tmp_path, "update", f"--url=jdbc:sqlite:{db}")
    assert f"LIQUIBASE_CHANGELOG={CHANGELOG}" in args


def test_wrapper_forwards_caller_subcommand(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, args = _run_wrapper(
        tmp_path,
        "rollback-count",
        f"--url=jdbc:sqlite:{db}",
        f"--changelog-file={CHANGELOG}",
    )
    assert "LIQUIBASE_ACTION=rollback-count" in args


def test_wrapper_preserves_spaces_in_database_filename(tmp_path: Path) -> None:
    db = _db(tmp_path, name="my expenses.db")
    result, args = _run_wrapper(
        tmp_path, "update", f"--url=jdbc:sqlite:{db}", f"--changelog-file={CHANGELOG}"
    )
    assert result.returncode == 0
    assert "LIQUIBASE_DB_FILE=my expenses.db" in args


def test_wrapper_propagates_docker_failure(tmp_path: Path) -> None:
    db = _db(tmp_path)
    result, _ = _run_wrapper(
        tmp_path,
        "update",
        f"--url=jdbc:sqlite:{db}",
        f"--changelog-file={CHANGELOG}",
        docker_rc=7,
    )
    assert result.returncode == 7


def test_wrapper_rejects_non_sqlite_url(tmp_path: Path) -> None:
    result, _ = _run_wrapper(
        tmp_path,
        "update",
        "--url=jdbc:postgresql://host/db",
        f"--changelog-file={CHANGELOG}",
    )
    assert result.returncode == 2
    assert "only --url=jdbc:sqlite:<path> is supported" in result.stderr
