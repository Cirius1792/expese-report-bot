# Expectations: Liquibase Schema Migrations

## Happy path

- The changelog at `db/changelog/db.changelog.xml` is an XML Liquibase changelog whose first changeset creates the `expenses` table with the full current schema (id, amount, currency, merchant, date, category, user_id, receipt_photo_id, created_at, deleted_at).
- Running `liquibase update` against a **fresh** empty database file creates the `expenses` table, the `databasechangelog` table, and the `databasechangeloglock` table, and exits 0.
- Running `liquibase update` a second time against the same database is a no-op (no new changesets) and exits 0.
- `SqliteExpenseRepository` opens a migrated database and all port operations (save, get_by_id, get_by_user_and_month, get_months_with_expenses, get_total_by_user_and_year, delete_by_id) work unchanged.
- The container entrypoint script runs `liquibase update` against `EXPENSE_DB_PATH` and only then `exec`s the bot; the bot process ends up as the container's main process.
- The `expense-extract` CLI runs `liquibase update` against its `--db` path before opening the repository, so it works against both fresh and pre-existing database files.
- CI and the release pipeline call the reusable `.github/workflows/tests.yml`, which pulls the Liquibase 4.33.0 image and runs the full pytest profile (`uv run pytest -o addopts=""`, unit + integration) plus BDD; the wrapper is resolved by absolute path, never copied onto `PATH`.
- The test suite is split by capability: a plain `uv run pytest` runs the hermetic unit suite (no Docker, no `liquibase` on `PATH`) and passes; `uv run pytest -o addopts=""` runs the full suite including integration tests; `uv run pytest -o addopts="" -m integration` runs only the integration tests and fails loudly with an actionable message when Docker is unavailable.
- The Docker image embeds the Liquibase CLI (official 4.33.0 image base, which bundles the SQLite JDBC driver) and the entrypoint script; `docker build` succeeds.

## Edge cases

- A database file whose `expenses` table **lacks** `deleted_at` (pre-ADR-0011 schema) is upgraded by `liquibase update`: the column is added, existing rows read as not-deleted, and the changeset is recorded in `databasechangelog`.
- A database file whose `expenses` table already matches the current schema is untouched by `liquibase update` (both baseline changesets are no-ops) and no data is modified.
- Test fixtures that previously used `:memory:` databases use temp-file databases: hermetic fixtures apply the generated snapshot (`tests/_schema/expenses.sql`), and integration fixtures migrate a temp file with the real `liquibase update`; the actual changelog is exercised by the integration tests.
- The behave BDD environment migrates its database file before scenarios run.
- If the `liquibase` binary is not available where the CLI tests run, the failure is loud (non-zero exit, clear error), not silent.

## Behaviors that must NOT happen

- `SqliteExpenseRepository` must not create, alter, or migrate any schema. No `CREATE TABLE`, `ALTER TABLE`, or `PRAGMA table_info`-driven migration code remains in the adapter.
- No **hand-authored** schema definition may exist. Test and BDD databases obtain the schema either by running the changelog, or from `tests/_schema/expenses.sql` — a **generated** artifact that covers every application-owned schema object and embeds the changelog's SHA-256, so `tests/migrations/test_schema_snapshot.py` fails hermetically on any changelog edit until the artifact is regenerated (and fails against the real changelog output in the integration profile). (Deliberate exception: `tests/migrations/test_changelog.py` recreates a **legacy** pre-`deleted_at` schema to prove the upgrade path.)
- The bot must not start if `liquibase update` fails (the entrypoint exits non-zero before the bot process is launched).
- Applied changesets must never be edited in place; new schema changes are new changesets appended to the changelog.
- The `databasechangelog` / `databasechangeloglock` tables must not be dropped, renamed, or modified by application code.
- Domain and port layers must remain free of any Liquibase, migration, or DDL concerns (hexagonal boundary intact).
- Migrations must not run in parallel against the same database file from application code (single entry-point rule: the entrypoint script and the CLI are the only migrators, each sequentially before DB use).
- No SQLite JDBC driver jars may be committed to the repo (no `lib/*.jar`): the driver ships inside the Liquibase 4.33.0 image, and the wrapper/entrypoint must pass **no** `--classpath`.

## Evidence mapping

- Pytest: `tests/migrations/test_changelog.py` (or equivalent) proves: fresh-DB migration creates the expected schema; re-run is a no-op; legacy DB (without `deleted_at`) is upgraded.
- Pytest: `tests/migrations/test_liquibase_tooling.py` proves the jar-free invariant — the wrapper/`Dockerfile`/CI pin `liquibase/liquibase:4.33.0`, no `--classpath=` is passed, and no `lib/*.jar` is committed.
- Pytest: `tests/migrations/test_schema_snapshot.py::test_snapshot_matches_changelog` (integration) proves the generated snapshot still equals the changelog output.
- Pytest: `tests/adapters/out/test_sqlite_repository*.py` and `tests/adapters/inbound/test_cli_extraction.py` pass as hermetic unit tests, proving the adapter is unchanged in behavior with schema ownership removed.
- Behave: `uv run behave` passes with the migrated-database environment.
- Pytest: `tests/migrations/test_ci_workflows.py` proves both CI and release call the reusable tests workflow, that it runs the full profile and BDD, and that no workflow falls back to a bare `uv run pytest` or copies the wrapper onto `PATH`.
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
