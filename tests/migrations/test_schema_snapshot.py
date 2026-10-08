"""Guards for the generated schema snapshot (ADR 0014).

The snapshot is legitimate only while it is provably derived from the changelog:

- ``test_snapshot_records_current_changelog_digest`` (hermetic) fails the moment
  the changelog is edited without regenerating the snapshot.
- ``test_snapshot_matches_changelog`` (integration) fails when the snapshot no
  longer matches what Liquibase actually produces.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests._schema import (
    SNAPSHOT_PATH,
    apply_snapshot,
    changelog_digest,
    dump_application_schema,
    render_snapshot,
)


def test_snapshot_records_current_changelog_digest() -> None:
    """Any changelog edit without regeneration must fail — no Docker required."""
    assert changelog_digest() in SNAPSHOT_PATH.read_text(encoding="utf-8")


def test_schema_dump_changes_when_a_non_table_object_is_added(tmp_path: Path) -> None:
    """The dump covers indexes/triggers/views, not just the expenses table."""
    db = tmp_path / "indexed.db"
    apply_snapshot(db)
    before = dump_application_schema(db)
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE INDEX idx_expenses_merchant ON expenses (merchant)")
    assert dump_application_schema(db) != before


@pytest.mark.integration
def test_snapshot_matches_changelog() -> None:
    assert SNAPSHOT_PATH.read_text(encoding="utf-8") == render_snapshot()
