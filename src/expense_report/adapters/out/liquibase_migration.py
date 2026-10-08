"""Driven adapter that runs the Liquibase CLI before any database use (ADR 0013).

Every entry point must migrate before opening the database. This module is the
single owner of that step, so the invariant has exactly one implementation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_CHANGELOG = "db/changelog/db.changelog.xml"


def ensure_database_migrated(db_path: str | Path) -> None:
    """Run ``liquibase update`` so the schema is current before the DB is opened.

    ``db_path`` must already be absolute: the command runs with the repository
    root as its working directory, so a relative path would resolve to a
    different file than the caller's own working directory.
    """
    repo_root = Path(__file__).resolve().parents[4]
    subprocess.run(
        [
            "liquibase",
            "--validate-xml-changelog-files=false",
            "update",
            f"--url=jdbc:sqlite:{db_path}",
            f"--changelog-file={_CHANGELOG}",
        ],
        cwd=repo_root,
        check=True,
    )
