"""Print a JSON snapshot of an expenses database for the upgrade probe."""

from __future__ import annotations

import json
import sqlite3
import sys


def snapshot(db_path: str) -> dict[str, object]:
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0].lower()
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        columns: list[str] = []
        rows: list[dict[str, object]] = []
        if "expenses" in tables:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(expenses)")]
            rows = [
                {"id": row[0], "amount": row[1], "currency": row[2], "merchant": row[3]}
                for row in connection.execute(
                    "SELECT id, amount, currency, merchant FROM expenses ORDER BY id"
                )
            ]
        changesets = 0
        if "databasechangelog" in tables:
            changesets = connection.execute("SELECT COUNT(*) FROM databasechangelog").fetchone()[0]
    return {
        "tables": sorted(tables),
        "columns": columns,
        "rows": rows,
        "changesets": changesets,
    }


if __name__ == "__main__":
    print(json.dumps(snapshot(sys.argv[1])))
