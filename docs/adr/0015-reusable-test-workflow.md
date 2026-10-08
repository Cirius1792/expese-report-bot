# ADR 0015: Reusable test workflow as the single pipeline contract

**Date:** 2026-10-08
**Status:** Accepted

## Context

ADR 0014 split the suite by capability: `uv run pytest` runs the hermetic unit
profile, and only `uv run pytest -o addopts=""` runs the integration tests
(including the schema-snapshot drift guard). The pipelines predate that split:

- `.github/workflows/ci.yml` ran the full profile (with coverage) but carried a
  now-redundant "Install Liquibase" step that copied `scripts/liquibase` onto
  `PATH`.
- `.github/workflows/release.yml` ran a bare `uv run pytest`. After ADR 0014
  that silently ran unit tests only — the snapshot drift guard would not run at
  release time — and it never pulled the pinned Liquibase image.

Two callers each carrying their own copy of "how to test" is what let
`release.yml` drift out of sync with the suite.

## Decision

1. A new reusable workflow `.github/workflows/tests.yml` (`on: workflow_call`)
   owns the test contract: a `pytest` job running
   `uv run pytest -o addopts="" --cov=expense_report` (the full profile,
   ADR 0014) and a `bdd` job (`needs: pytest`) running `uv run behave`. Both
   jobs pull `liquibase/liquibase:4.33.0`.
2. `.github/workflows/ci.yml` calls it with `upload-coverage: true`; its
   `generate-badge` job keeps the `coverage-data` artifact contract (ADR 0012).
3. `.github/workflows/release.yml` calls it unchanged; `build-push` still
   `needs:` the test job.
4. The `cp scripts/liquibase /usr/local/bin/liquibase` step is deleted from
   both callers: tests resolve the wrapper by absolute path (ADR 0014) and
   behave self-provisions `scripts/` on `PATH`.
5. `ci.yml` is not renamed, so the README tests badge URL (ADR 0012) survives.

## Consequences

- The split-profile commands live in exactly one file, so a caller cannot drift
  back to a bare `uv run pytest`. `tests/migrations/test_ci_workflows.py` pins
  this (both callers call the reusable workflow; no workflow runs bare pytest;
  no workflow copies the wrapper onto `PATH`), and
  `tests/migrations/test_liquibase_tooling.py` pins the image across all
  workflow files.
- GitHub logs are nested one level for the test jobs.
- The deferred `Makefile` (ADR 0014) remains useful as the local front door;
  the reusable workflow additionally owns job topology and the coverage
  artifact, so the Makefile does not make it redundant.
- ADR 0012's `unit-tests` / `bdd-tests` job names are historical; the coverage
  *contract* it records is unchanged.

## Alternatives considered

- **Inline the fix in both workflows** — smaller diff, but leaves the exact
  duplication that caused the release drift.
- **Call `ci.yml` itself via `workflow_call`** — mixes triggers and is harder
  to follow than a dedicated reusable workflow.
