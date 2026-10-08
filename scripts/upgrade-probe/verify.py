"""Assert the upgrade probe's before/after snapshots prove a safe migration."""

from __future__ import annotations

import json
import sys


def main() -> int:
    before = json.loads(sys.argv[1])
    after = json.loads(sys.argv[2])

    assert "deleted_at" not in before["columns"], f"legacy schema already has deleted_at: {before}"
    assert "databasechangelog" not in before["tables"], f"legacy schema has tracking: {before}"
    assert before["rows"], "legacy database has no rows"

    assert "deleted_at" in after["columns"], f"PR schema missing deleted_at: {after}"
    assert "databasechangelog" in after["tables"], f"Liquibase tracking table missing: {after}"
    assert after["changesets"] == 2, f"expected 2 baseline changesets: {after}"
    assert after["rows"] == before["rows"], "migration changed or lost expense rows"
    print("PASS: legacy rows preserved, deleted_at added, Liquibase baselined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
