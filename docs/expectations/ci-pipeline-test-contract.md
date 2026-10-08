# Expectations: CI Pipeline Test Contract

**Scope:** `.github/workflows/` only (`ci.yml`, `release.yml`, new `tests.yml`).
No `src/` changes. Consumes ADR 0014's split-profile contract (hermetic unit
profile by default; full profile is `-o addopts=""`).

## Happy path

- Both pipelines call the reusable tests workflow via
  `uses: ./.github/workflows/tests.yml`:
  - `.github/workflows/ci.yml` (push to `main`, PRs to `main`), and
  - `.github/workflows/release.yml` (tag push), whose `build-push` job still
    `needs:` the tests outcome.
- The reusable `.github/workflows/tests.yml`:
  - runs the **full** pytest profile — `uv run pytest -o addopts=""` — so the
    integration tests and the snapshot drift guard (ADR 0014) always execute,
  - then runs `uv run behave` (BDD, needs Docker),
  - pulls the pinned image `docker pull liquibase/liquibase:4.33.0` before
    running either suite.
- `ci.yml` passes `upload-coverage: true`; the reusable workflow uploads the
  `coverage-data` artifact and the `generate-badge` job still downloads it and
  advances `coverage.svg` only on push to `main`.
- The `ci.yml` filename is unchanged, so the README tests badge URL
  (`.../workflows/ci.yml/badge.svg`, ADR 0012) keeps working.

## Edge cases

- The Liquibase image pin lives in exactly one workflow file (the reusable
  one); `tests/migrations/test_liquibase_tooling.py` proves the pin is present
  and that no workflow references the `5.0.4` image.
- `generate-badge` still runs only on `push` to `refs/heads/main` — never on PR
  heads or on tag-triggered release runs.
- `release.yml` passes no inputs, so `upload-coverage` defaults to `false` and
  no coverage artifact is produced during a release.

## Behaviors that must NOT happen

- No workflow runs a bare `uv run pytest`. The default profile is hermetic
  (unit only), so a bare invocation silently drops the integration tests and
  the snapshot drift guard — the exact defect this change fixes (ADR 0014).
- No workflow copies the wrapper onto `PATH` (`cp scripts/liquibase
  /usr/local/bin/liquibase`). Tests resolve `scripts/liquibase` by absolute
  path and behave self-provisions `scripts/` on `PATH`.
- The reusable workflow must not skip BDD.
- `release.yml` must not build or push the image when the tests workflow fails.

## Evidence mapping

- Pytest: `tests/migrations/test_ci_workflows.py` proves both pipelines call the reusable
  workflow, that it runs the full profile and BDD, that no workflow runs a bare
  `uv run pytest`, and that no workflow copies the wrapper onto `PATH`.
- Pytest: `tests/migrations/test_liquibase_tooling.py::test_workflows_pin_bundled_driver_image`
  proves the pinned image is present across the workflow files and `5.0.4` is
  absent.
- Shell: every workflow file parses as YAML
  (`uv run --with pyyaml python -c "import yaml, pathlib; ..."`).
- Local `act`: `tests/Tests/pytest` ran the full profile in a real runner
  (332 passed) and uploaded the `coverage-data` artifact; `tests/Tests/bdd`
  passed. See the evidence log below.
- GitHub Actions: pushing the branch and watching a real `ci.yml` run remains
  the final end-to-end proof (requires the user's go-ahead — not done in-loop).

## Evidence log — executed 2026-10-08

The Liquibase wrapper shells out to a *nested* `docker run`, so `act` needs the
shim dir shared between the job container and the host daemon, and the
artifact server advertised on a host-reachable address:

```bash
mkdir -p /tmp/liquibase-shim && chmod 777 /tmp/liquibase-shim
act -W .github/workflows/ci.yml -j tests \
  --artifact-server-path /tmp/act-artifacts \
  --artifact-server-addr "$(hostname -I | awk '{print $1}')" \
  --container-options "-v /tmp/liquibase-shim:/tmp/liquibase-shim"
```

| Expectation | Executed evidence |
|---|---|
| Workflows are valid | `act --validate` → no errors |
| `ci.yml` calls the reusable workflow | `act -l` / `act -n` show `ci.yml` job `tests` → `Tests/pytest`, `Tests/bdd` |
| `release.yml` calls the reusable workflow | `act -W .github/workflows/release.yml -j tests -n` → `Release/validate-version` then `tests/Tests/pytest` |
| Reusable workflow runs the full profile | act run: `332 passed in 31.36s`; step `Run full test suite (unit + integration)` ✅ |
| Coverage artifact contract | `Artifact coverage-data has been successfully uploaded! Final size is 3008 bytes` |
| Reusable workflow runs BDD | step `Run BDD tests` ✅ → 35 scenarios / 267 steps passed |
| End-to-end job result | `Tests/pytest` 🏁 Job succeeded; `Tests/bdd` 🏁 Job succeeded; act exit 0 |
