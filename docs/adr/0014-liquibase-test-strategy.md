# ADR 0014: Test strategy for the Liquibase-owned schema

**Date:** 2026-10-08
**Status:** Accepted

## Context

ADR 0013 moved database schema ownership to Liquibase and retired `:memory:`
test databases. The suite then obtained its schema by shelling out to
`liquibase update` through the `scripts/liquibase` wrapper — from four
independent places (`tests/conftest.py`, and local `migrated_db()` helpers in
`tests/adapters/out/test_sqlite_repository.py`,
`tests/adapters/out/test_sqlite_repository_logging.py`, plus
`tests/migrations/test_changelog.py` and `cli_extraction.main()`), each of
which resolved the wrapper **by name through `PATH`**.

That produced two defects:

- **Not reproducible.** With the wrapper absent from `PATH`, a plain
  `uv run pytest` failed 27 tests and errored 25 more with
  `NotADirectoryError` / `FileNotFoundError: 'liquibase'`. CI only masked it by
  copying the wrapper to `/usr/local/bin/liquibase`; a developer's shell had to
  export `PATH` manually.
- **Slow and duplicated.** The repository fixtures were function-scoped, so a
  full run performed roughly 48 `docker run` invocations (25 repository + 6
  logging + 14 CLI + 3 changelog), taking ~200 s. Two `migrated_db()` helpers
  were copy-pasted, and a session-scoped `migrated_database` conftest fixture
  was dead code.

## Decision

1. **Split the suite by capability, not by layer.**
   - *unit* (default): hermetic — no Docker, no external binary.
   - *integration* (`pytest.mark.integration`): requires Docker and the pinned
     `liquibase/liquibase:4.33.0` image.

2. **The default profile is hermetic.** `addopts = "--strict-markers -m 'not
   integration'"`, so `uv run pytest` runs unit tests only. The full suite is
   `uv run pytest -o addopts=""`; the integration subset is
   `uv run pytest -o addopts="" -m integration`. **CI runs the full suite**, so
   the integration tests — and the drift guard below — always execute there.
   (A `Makefile` front door exposing `test` / `test-integration` / `test-all` /
   `provision` is deferred to a later increment; until it lands, the pytest
   invocations above are the contract.)

3. **The changelog remains the single source of truth.**
   `tests/_schema/expenses.sql` is a **generated** artifact — dumped from a real
   migration by `uv run python -m tests._schema --write` — and is legitimate
   only while `tests/migrations/test_schema_snapshot.py` proves it byte-identical
   to the changelog's output. A hand-edited snapshot, or a changelog change
   without regeneration, fails that test.

4. **The wrapper is resolved by absolute path** (`<repo>/scripts/liquibase`) in
   tests — never through `PATH`. Production keeps invoking `liquibase` from the
   image's `PATH` (`docker-entrypoint.sh`, `expense-extract`).

5. **Missing Docker in the integration profile fails loudly** — with an
   actionable message from `tests/_schema.require_docker()` — never a silent
   skip and never a pass.

## Consequences

- `uv run pytest` is hermetic and fast, and still covers the SQLite adapter
  (through the snapshot rather than through Liquibase).
- The integration surface shrinks to **4 tests** (3 changelog + 1 drift), and
  `docker run` calls per full run drop from ~48 to 4.
- A new failure mode is introduced: the snapshot can rot when the changelog
  changes and nobody regenerates it. The drift test is the guard, which is why
  CI must run the full profile.
- Until the `Makefile` lands, the invocations must be remembered (documented in
  `AGENTS.md`).
- Only the ordering test and the Docker smoke test still prove that the
  production entry points migrate before opening the database.

## Alternatives considered

- **Testcontainers (`testcontainers-python`)** — rejected. Verified by
  introspecting the installed package: it ships 52 modules and **none is
  `liquibase`** (the docs' `modules/liquibase.html` returns 404), so it would
  require a bespoke container built from the generic `DockerContainer`. It still
  requires a Docker daemon, still requires a bind-mounted SQLite file with the
  same uid-1001 permission handling, cannot satisfy tests that call
  `main()`'s `subprocess.run(["liquibase", ...])`, and would move tests off the
  wrapper that production and CI actually use.
- **Commit a hand-written schema** — rejected: a second source of truth that
  drifts silently. The generated snapshot plus drift test is the guarded variant.
- **Skip Liquibase-dependent tests when Docker is absent** — rejected: the
  expectations require loud failure, not silent skips.
- **Keep the wide integration set (no snapshot)** — rejected: the default
  profile would then lose all coverage of the SQLite adapter.
