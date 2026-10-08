"""Executable acceptance tests for the Liquibase schema changelog."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tests._schema import migrate_with_liquibase

pytestmark = pytest.mark.integration


def test_fresh_database_gets_schema_and_tracking_tables(tmp_path: Path) -> None:
    db = tmp_path / "fresh.db"
    migrate_with_liquibase(db)
    with sqlite3.connect(db) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        columns = {row[1] for row in connection.execute("PRAGMA table_info(expenses)")}
    # Liquibase creates tracking tables in uppercase on SQLite.
    tables_lower = {t.lower() for t in tables}
    assert {"expenses", "databasechangelog", "databasechangeloglock"} <= tables_lower
    assert "deleted_at" in columns


def test_reapplying_changelog_is_no_op(tmp_path: Path) -> None:
    db = tmp_path / "repeat.db"
    migrate_with_liquibase(db)
    with sqlite3.connect(db) as connection:
        before = connection.execute("SELECT COUNT(*) FROM databasechangelog").fetchone()[0]
    migrate_with_liquibase(db)
    with sqlite3.connect(db) as connection:
        after = connection.execute("SELECT COUNT(*) FROM databasechangelog").fetchone()[0]
    assert after == before == 2


def test_legacy_database_gains_deleted_at_without_losing_rows(tmp_path: Path) -> None:
    db = tmp_path / "legacy.db"
    # Seed a pre-ADR-0011 schema (no deleted_at column) with one row.
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            CREATE TABLE expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                merchant TEXT NOT NULL,
                date TEXT NOT NULL,
                category TEXT,
                user_id INTEGER NOT NULL,
                receipt_photo_id TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO expenses (amount, currency, merchant, date, user_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("10.00", "EUR", "Legacy Shop", "2026-07-01", 42, "2026-07-01T12:00:00"),
        )
        connection.commit()
    migrate_with_liquibase(db)
    with sqlite3.connect(db) as connection:
        row = connection.execute("SELECT merchant, deleted_at FROM expenses").fetchone()
        assert row == ("Legacy Shop", None)
        assert connection.execute("SELECT COUNT(*) FROM databasechangelog").fetchone()[0] == 2
