# Upgrade probe: v0.7.0 → Liquibase

Opt-in, end-to-end check that a database written by the **latest tagged
release** survives the migration introduced by ADR 0013. It is not part of CI
because it pulls a pinned historical image from `ghcr.io`.

## What it proves

1. The released v0.7.0 image creates its legacy schema (`expenses` **without**
   `deleted_at`, no Liquibase tracking tables) and writes real rows through its
   real `expense-extract` CLI.
2. The PR image's **real entrypoint** migrates that database: `deleted_at` is
   added, `databasechangelog` / `databasechangeloglock` appear with the two
   baseline changesets, and the legacy rows are preserved byte-for-byte.
3. The PR's `SqliteExpenseRepository` reads the migrated rows back.

The v0.7.0 tag predates both ADR 0011 (logical deletion) and ADR 0013
(Liquibase ownership), so this is a genuine cross-version schema change — not
just tracking-table bookkeeping.

## How the LLM is stubbed

`expense-extract` calls the LLM through `dspy`. `sitecustomize.py` replaces
`dspy` in `sys.modules` before the CLI imports it, returning a fixed prediction
from `STUB_*` environment variables. The CLI, use case, domain validation and
repository all run unchanged; only the network LLM call is faked. This mirrors
the boundary mock in `features/environment.py` and avoids a fake HTTP server
whose response format is dspy-version-sensitive.

## Run it

```bash
docker build -t expense-report-bot:local .
docker pull ghcr.io/cirius1792/spencer-bot:0.7.0
scripts/upgrade-probe/run.sh
# override either side if needed:
#   OLD_IMAGE=ghcr.io/cirius1792/spencer-bot:0.6.0 NEW_IMAGE=my-bot:tag scripts/upgrade-probe/run.sh
```

`run.sh` exits non-zero if any assertion fails.

## Files

| File | Purpose |
|------|---------|
| `run.sh` | Orchestrates seed → snapshot → migrate → verify → read-back |
| `sitecustomize.py` | Stubbed `dspy` LLM boundary (`PYTHONPATH=/stub`) |
| `inspect_db.py` | JSON snapshot of tables/columns/rows/changesets |
| `verify.py` | Asserts the before/after snapshots |
| `read_back.py` | Reads migrated rows with the PR repository |
