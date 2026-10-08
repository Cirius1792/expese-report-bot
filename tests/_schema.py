"""Schema provisioning seam for the test suite (ADR 0013, ADR 0014).

Two ways to give a test database its schema:

- ``migrate_with_liquibase`` — runs the real changelog through the
  ``scripts/liquibase`` wrapper (integration tests only, needs Docker).
- ``apply_snapshot`` — applies ``tests/_schema/expenses.sql``, a *generated*
  artifact whose validity is guarded by
  ``tests/migrations/test_schema_snapshot.py`` (hermetic unit tests).

The wrapper is resolved by absolute path on purpose: realising it through
``PATH`` is what made the suite non-reproducible before ADR 0014.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[1]
LIQUIBASE_WRAPPER: Path = REPO_ROOT / "scripts" / "liquibase"
CHANGELOG: str = "db/changelog/db.changelog.xml"
SNAPSHOT_PATH: Path = REPO_ROOT / "tests" / "_schema" / "expenses.sql"
LIQUIBASE_IMAGE: str = "liquibase/liquibase:4.33.0"

_DOCKER_REQUIRED_MESSAGE = (
    "Docker is required for integration tests but the daemon is unreachable. "
    "Start Docker, then pull the pinned image: docker pull " + LIQUIBASE_IMAGE
)


def docker_available() -> bool:
    """Return whether a usable Docker daemon is reachable."""
    if shutil.which("docker") is None:
        return False
    result = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def require_docker() -> None:
    """Raise with an actionable message when Docker is not usable."""
    if not docker_available():
        raise RuntimeError(_DOCKER_REQUIRED_MESSAGE)


def migrate_with_liquibase(db_path: Path) -> None:
    """Migrate ``db_path`` by running the real changelog through the wrapper."""
    require_docker()
    subprocess.run(
        [
            str(LIQUIBASE_WRAPPER),
            "update",
            f"--url=jdbc:sqlite:{db_path}",
            f"--changelog-file={CHANGELOG}",
        ],
        cwd=REPO_ROOT,
        check=True,
    )


def apply_snapshot(db_path: Path) -> None:
    """Apply the generated schema snapshot to ``db_path`` (no Docker)."""
    if not SNAPSHOT_PATH.is_file():
        raise RuntimeError(
            f"schema snapshot missing at {SNAPSHOT_PATH}; "
            "regenerate it with: uv run python -m tests._schema --write"
        )
    with sqlite3.connect(str(db_path)) as connection:
        connection.executescript(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def dump_expenses_ddl(db_path: Path) -> str:
    """Return the normalised ``CREATE TABLE`` DDL for the ``expenses`` table."""
    with sqlite3.connect(str(db_path)) as connection:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'expenses'"
        ).fetchone()
    if row is None or row[0] is None:
        raise RuntimeError(f"no 'expenses' table found in {db_path}")
    ddl: str = row[0]
    return ddl.strip().rstrip(";") + ";\n"


def render_snapshot() -> str:
    """Migrate a throwaway database and return the resulting ``expenses`` DDL."""
    require_docker()
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "snapshot.db"
        migrate_with_liquibase(db_path)
        return dump_expenses_ddl(db_path)


def write_snapshot() -> None:
    """Regenerate the committed schema snapshot from the changelog."""
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(render_snapshot(), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: ``python -m tests._schema --write``."""
    parser = argparse.ArgumentParser(description="Manage the schema snapshot.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenerate tests/_schema/expenses.sql from the changelog",
    )
    args = parser.parse_args(argv)
    if not args.write:
        parser.print_help()
        return 2
    write_snapshot()
    print(f"wrote {SNAPSHOT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
