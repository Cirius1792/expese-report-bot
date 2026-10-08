# ADR 0013: Liquibase for Database Schema Migrations

**Date:** 2026-07-20
**Revised:** 2026-10-08 — switched from Liquibase 5.0.4 + committed `lib/`
jars to the 4.33.0 image (which bundles the SQLite driver); see "Verified
findings" and "Alternatives considered" below.
**Status:** Accepted

## Context

The `expenses` table schema was managed inline in `SqliteExpenseRepository`:
`_create_table()` ran `CREATE TABLE IF NOT EXISTS` on every startup, and
`_migrate_schema()` performed an ad-hoc `ALTER TABLE` (ADR 0011) guarded by a
`PRAGMA table_info` check. This works for one table, but it has no history, no
reviewable trail of what changed when, no way to verify migrations apply
cleanly before deploy, and no consolidated process for the next schema change.
The bot is already in production use, so schema changes now require a
reliable, auditable migration process.

## Decision

Adopt **Liquibase** (Community, Apache-2.0, v4.33.0) as the single owner of
database schema state, using the official CLI with an **XML** changelog.

### Changelog

- Location: `db/changelog/db.changelog.xml` (XML, not formatted SQL): the
  baseline needs a `sqlCheck` precondition to guard the legacy-DB self-heal,
  and XML gives preconditions first-class support (verified on 4.33.0 — see
  "Verified findings" below).
- No `liquibase.properties`; `--url` and `--changelog-file` are passed
  explicitly at every call site, as a **relative** path (absolute changelog
  paths are not resolved reliably; verified on 4.33.0).
- XML changelogs run with `--validate-xml-changelog-files=false` so no remote
  XSD fetch happens at container start (offline-safe).
- Baseline changesets (both idempotent, verified against Liquibase 4.33.0):
  1. `CREATE TABLE IF NOT EXISTS expenses` (raw SQL) with the full current
     schema.
  2. `ALTER TABLE expenses ADD COLUMN deleted_at TEXT` guarded by
     `<not><sqlCheck expectedResult="1">SELECT CASE WHEN EXISTS
     (SELECT 1 FROM pragma_table_info('expenses') WHERE name = 'deleted_at')
     THEN '1' ELSE '0' END</sqlCheck></not>` with `onFail=MARK_RAN`,
     preserving the pre-ADR-0011 self-heal behavior.
- Applied changesets are immutable; future changes append new changesets.

## Verified findings (Liquibase 4.33.0 + SQLite, 2026-10-08)

Verified by executing the real official image (bundled SQLite JDBC driver, no
`--classpath`) against fresh, re-run, legacy, and current-schema databases:

- The bundled `sqlite-jdbc` driver (3.50.2.0) is picked up automatically — no
  `--classpath` and no committed driver jars are needed.
- `sqlCheck` requires `expectedResult`; with it, the check query must always
  return exactly one row (a zero-row result is a precondition *error*), hence
  the `CASE WHEN EXISTS` formulation.
- The XML `sqlCheck` precondition with `onFail=MARK_RAN` behaves correctly:
  it skips the `ALTER TABLE` on a current-schema database (no duplicate-column
  error) and runs it on a legacy database (column added, rows preserved).
- `--validate-xml-changelog-files` is honoured and must be set to `false`: its
  default (`true`) fetches the XSD from liquibase.org at runtime, which fails
  in offline deployments.
- `--changelog-file` is resolved against the search path / CWD, so it is passed
  as a **relative** path (from the repo root via `--searchPath`, or
  `changelog/db.changelog.xml` from `/app/db` in the container).
- The structured `<createTable>` change is not idempotent; the baseline uses
  raw `CREATE TABLE IF NOT EXISTS`.

### Why 4.33.0 (and not 5.x)

Liquibase 5.x **removed** the bundled JDBC drivers and expects them to be
added via the `lpm` package manager, which is unreliable in restricted
networks (checksum-validation failures). 4.33.0 is the last release line that
ships the SQLite driver inside the official image, which keeps the repository
free of committed binaries and removes every `--classpath`. The trade-off is a
larger base image (~1.1 GB vs ~0.4 GB for 5.x) and an older Liquibase major —
acceptable for a single-user, single-container deployment.

### Docker image build (verified 2026-10-08)

Verified by building the image and running the entrypoint end-to-end:

- The official Liquibase image runs as the unprivileged `liquibase` user, so
  the `Dockerfile` switches to `USER root` for its build steps (`chmod`,
  `groupadd`, `useradd`) and restores a non-root `USER` at the end. Without
  this the build fails with "Operation not permitted".
- uv installs its managed CPython under `$HOME/.local/share/uv/python`
  (`/root/...` during the build); because `/root` is mode `0700`, the venv's
  `python` symlink is unreachable for the runtime user. Building with
  `UV_PYTHON_INSTALL_DIR=/opt/python` (made world-readable) fixes the
  "Permission denied" seen when the container tried to launch the bot.
- End-to-end: a legacy database bind-mounted at `/data` is migrated (column
  added, rows preserved), then the bot is `exec`'d as the container's PID 1.
  With an unwritable database the entrypoint exits non-zero and the bot never
  starts.

### Schema ownership transfer

- `_create_table()` and `_migrate_schema()` are **removed** from
  `SqliteExpenseRepository`. The adapter assumes a migrated database and
  performs no DDL.
- The invariant: **no entry point opens the database without running
  `liquibase update` first**.
  - Container: `docker-entrypoint.sh` runs
    `liquibase update --url=jdbc:sqlite:${EXPENSE_DB_PATH} --changelog-file=...`
    then `exec`s the bot (bot stays PID 1; a failed migration exits non-zero
    and the bot never starts).
  - `expense-extract` CLI: runs `liquibase update` against its `--db` path
    before opening the repository.
  - Tests/BDD: fixtures run the real `liquibase update` binary against a
    temp-file database (session-scoped, migrated once, per-test cleanup).
    `:memory:` databases are retired from the test suite because an external
    Liquibase process cannot reach them.

### Tooling

- The Docker image is based on the official `liquibase/liquibase:4.33.0`
  image (CLI + Java runtime + bundled SQLite JDBC driver). No driver jars are
  committed to the repository.
- Local dev and CI use the committed wrapper `scripts/liquibase`, which runs
  the same official image via Docker (stages the DB file for the container's
  non-root user, forces the offline XML-validation flag, uses `--searchPath`
  for the changelog). No standalone CLI install is required.
- `ci.yml` pulls the image and copies the wrapper to `PATH`; the wrapper
  resolves the repo root from the checked-out working directory.
- Liquibase adds `databasechangelog` / `databasechangeloglock` tables to the
  database; application code never touches them.

## Consequences

- Schema changes are now: new changeset → review as a diff → verified in CI
  against a fresh DB → applied automatically at container start.
- The production database is baselined on first container start after deploy:
  both baseline changesets are no-ops against the current schema, and their
  application is recorded in `databasechangelog`.
- Test databases exercise the actual changelog (stronger than the old
  in-code DDL), at the cost of one Liquibase process start per test session.
- The `expense-extract` CLI depends on the `liquibase` binary being on PATH
  in development environments.
- SQLite `ALTER TABLE` limitations remain: future changes that SQLite cannot
  express directly (e.g., column type changes) will use table-rebuild
  changesets. Acceptable for a single-user, single-container deployment with
  brief downtime.
- ADR 0011's inline migration is superseded as a mechanism (its schema change
  remains part of the baselined schema); this ADR does not alter any
  user-facing behavior.

## Alternatives considered

- **Liquibase 5.0.4 with vendored/fetched driver jars**: keeps the newer major
  and its security hardening, but requires the SQLite JDBC + SLF4J jars
  (~13 MB) to be committed to the repo or downloaded by a setup script, and
  keeps every call site carrying a `--classpath`. Rejected in favour of
  4.33.0's bundled driver.
- **Alembic** (Python-native): good fit for Python, but weakest for raw-SQL
  SQLite workflows without SQLAlchemy models; team chose Liquibase for its
  consolidated, DB-agnostic, audit-friendly process.
- **dbmate / sqitch**: lighter CLIs, but less mature precondition/baseline
  tooling; Liquibase's precondition support was needed for the legacy-DB
  self-heal changeset.
- **Python in-code versioned migrations**: no external tool, but keeps schema
  logic in Python (second source of truth, no pre-deploy verification, no
  standard audit trail).
