# Expectations: Liquibase Schema Migrations

## Happy path

- The changelog at `db/changelog/db.changelog.xml` is an XML Liquibase changelog whose first changeset creates the `expenses` table with the full current schema (id, amount, currency, merchant, date, category, user_id, receipt_photo_id, created_at, deleted_at).
- Running `liquibase update` against a **fresh** empty database file creates the `expenses` table, the `databasechangelog` table, and the `databasechangeloglock` table, and exits 0.
- Running `liquibase update` a second time against the same database is a no-op (no new changesets) and exits 0.
- `SqliteExpenseRepository` opens a migrated database and all port operations (save, get_by_id, get_by_user_and_month, get_months_with_expenses, get_total_by_user_and_year, delete_by_id) work unchanged.
- The container entrypoint script runs `liquibase update` against `EXPENSE_DB_PATH` and only then `exec`s the bot; the bot process ends up as the container's main process.
- The `expense-extract` CLI runs `liquibase update` against its `--db` path before opening the repository, so it works against both fresh and pre-existing database files.
- CI pulls the Liquibase 4.33.0 image and puts the `scripts/liquibase` wrapper on PATH; the full unit + BDD suites pass with the real changelog applied to test databases.
- The Docker image embeds the Liquibase CLI (official 4.33.0 image base, which bundles the SQLite JDBC driver) and the entrypoint script; `docker build` succeeds.

## Edge cases

- A database file whose `expenses` table **lacks** `deleted_at` (pre-ADR-0011 schema) is upgraded by `liquibase update`: the column is added, existing rows read as not-deleted, and the changeset is recorded in `databasechangelog`.
- A database file whose `expenses` table already matches the current schema is untouched by `liquibase update` (both baseline changesets are no-ops) and no data is modified.
- Test fixtures that previously used `:memory:` databases use a temp-file database migrated once by the real `liquibase update` binary, with per-test cleanup, so the actual changelog is exercised.
- The behave BDD environment migrates its database file before scenarios run.
- If the `liquibase` binary is not available where the CLI tests run, the failure is loud (non-zero exit, clear error), not silent.

## Behaviors that must NOT happen

- `SqliteExpenseRepository` must not create, alter, or migrate any schema. No `CREATE TABLE`, `ALTER TABLE`, or `PRAGMA table_info`-driven migration code remains in the adapter.
- No second source of truth for the schema may exist: no hardcoded `CREATE TABLE` statements for the **current** `expenses` schema in `src/`, `tests/`, or `features/` — test fixtures obtain the schema by running the changelog, not by duplicating DDL. (Deliberate exception: `tests/migrations/test_changelog.py` recreates a **legacy** pre-`deleted_at` schema to prove the upgrade path — that is the pre-migration shape, the inverse of the current schema, not a duplicate of it.)
- The bot must not start if `liquibase update` fails (the entrypoint exits non-zero before the bot process is launched).
- Applied changesets must never be edited in place; new schema changes are new changesets appended to the changelog.
- The `databasechangelog` / `databasechangeloglock` tables must not be dropped, renamed, or modified by application code.
- Domain and port layers must remain free of any Liquibase, migration, or DDL concerns (hexagonal boundary intact).
- Migrations must not run in parallel against the same database file from application code (single entry-point rule: the entrypoint script and the CLI are the only migrators, each sequentially before DB use).
- No SQLite JDBC driver jars may be committed to the repo (no `lib/*.jar`): the driver ships inside the Liquibase 4.33.0 image, and the wrapper/entrypoint must pass **no** `--classpath`.

## Evidence mapping

- Pytest: `tests/migrations/test_changelog.py` (or equivalent) proves: fresh-DB migration creates the expected schema; re-run is a no-op; legacy DB (without `deleted_at`) is upgraded.
- Pytest: `tests/migrations/test_liquibase_tooling.py` proves the jar-free invariant — the wrapper/`Dockerfile`/CI pin `liquibase/liquibase:4.33.0`, no `--classpath=` is passed, and no `lib/*.jar` is committed.
- Pytest: existing `tests/adapters/out/test_sqlite_repository*.py` and `tests/adapters/inbound/test_cli_extraction.py` pass with fixtures driven by the real changelog, proving the adapter is unchanged in behavior with schema ownership removed.
- Behave: `uv run behave` passes with the migrated-database environment.
- Shell: the entrypoint script is executed (or its logic mirrored in a test) proving migration-then-exec ordering and non-zero exit on migration failure.
- Docker: `docker build` succeeds with the Liquibase CLI embedded (build output pasted as evidence).
- Full verification: `uvx ruff format`, `uvx ruff check`, `uvx ty check`, `uv run pytest`, `uv run behave`.

## Evidence log — executed 2026-10-08

Environment: `export PATH="$PWD/scripts:$PATH"` (wrapper `scripts/liquibase`,
image `liquibase/liquibase:4.33.0`, SQLite driver bundled).

| Expectation | Executed evidence |
|---|---|
| Fresh DB creates `expenses` + tracking tables | `pytest tests/migrations/` → `test_fresh_database_gets_schema_and_tracking_tables` PASS; manual image run → 10-column `expenses` + `DATABASECHANGELOG` + `DATABASECHANGELOGLOCK` |
| Re-run is a no-op | `test_reapplying_changelog_is_no_op` PASS; manual re-run → "Database is up to date, no changesets to execute" |
| Legacy DB upgraded, rows preserved | `test_legacy_database_gains_deleted_at_without_losing_rows` PASS; real container run on mounted legacy DB → `deleted_at` added, row `7.77/SmokeShop` intact, 2 changelog rows |
| Repository ops unchanged | `tests/adapters/out/test_sqlite_repository*.py` PASS |
| Container migrates then execs bot | `docker build` succeeds; container logs show `liquibase update` success, `ps` shows `expense-bot` as **PID 1** (PPID 0) |
| Migration failure blocks the bot | read-only `/data` run → `SQLITE_READONLY`, exit 1, **no bot process** |
| CLI self-migrates | `tests/adapters/inbound/test_cli_extraction.py` → 14 PASS (`main()` runs `liquibase update`) |
| CI pins the image | `test_ci_pins_bundled_driver_image` PASS |
| No DDL in `src/` (hexagonal boundary) | `grep -rniE "CREATE TABLE|ALTER TABLE|PRAGMA table_info" src/` → CLEAN |
| App never touches tracking tables | `grep -rniE "databasechangelog" src/` → CLEAN |
| No committed driver jars / no `--classpath` | `test_no_committed_driver_jars`, `test_wrapper_pins_bundled_driver_image_without_classpath`, `test_entrypoint_needs_no_classpath` PASS; `find . -name '*.jar'` → none |
| Behave passes on migrated DB | `uv run behave` → 8 features / 35 scenarios / 267 steps, 0 failed |
