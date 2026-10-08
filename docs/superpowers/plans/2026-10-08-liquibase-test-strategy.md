# Liquibase Test Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `uv run pytest` a hermetic unit-test run (no Docker, no `PATH` dependence) while the real Liquibase changelog keeps governing every test database through a generated schema snapshot guarded by a drift test.

**Architecture:** Split the suite by capability: unit tests (hermetic) and `integration` tests (Docker + Liquibase image). Schema *production* is separated from schema *consumption*: the changelog remains the single source of truth, a generated artifact (`tests/_schema/expenses.sql`) is the fast consumption path, and an integration drift test proves the artifact still equals the changelog output.

**Scope note:** the `Makefile` front door, provisioning target, and CI rewiring are **out of scope for this increment** (see "Deferred to a later increment"). This increment changes the test suite only.

**Tech Stack:** Python 3.12+, uv, pytest (+markers, `--strict-markers`), behave, ruff, ty, Docker, `liquibase/liquibase:4.33.0`.

**Spec:** `docs/adr/0013-liquibase-schema-migrations.md`, `docs/expectations/liquibase-schema-migrations.md`, and the new `docs/adr/0014-liquibase-test-strategy.md` written in Task 1.

## Global Constraints

- Python 3.12+; use `X | Y` unions. Strong typing on all signatures and attributes; no `Any`/untyped `dict` in signatures.
- Hexagonal boundaries: `src/expense_report/domain/` has zero framework/IO imports. `tests/_schema.py` is test-only and must not be imported by `src/`.
- Liquibase image pin is exactly `liquibase/liquibase:4.33.0` (bundles the SQLite driver; no `lib/` jars, no `--classpath`).
- Changelog path is exactly `db/changelog/db.changelog.xml`, always passed relative to the repo root.
- Never commit secrets; never bypass hooks (`--no-verify` / `SKIP=gitleaks`).
- Full battery after every change: `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest`.
- Markers are `--strict-markers`; the only custom marker is `integration`.
- Tests must never depend on the ambient `PATH` for `liquibase`; resolve the wrapper by absolute path.
- Commit messages follow the repo's Conventional Commits style (`feat:`, `test:`, `docs:`, `chore:`).

## Review Focus

Failure modes this plan must pin with tests (each gets a test in the owning task):

1. **Snapshot drift** — someone hand-edits `tests/_schema/expenses.sql`, or changes the changelog without regenerating: `test_snapshot_matches_changelog` must FAIL.
2. **Silent skip on missing Docker** — running the integration profile without a Docker daemon must FAIL LOUDLY with an actionable message, never silently pass or skip.
3. **Ambient `PATH` dependence** — `uv run pytest` on a machine where `liquibase` is not on `PATH` (and Docker unavailable) must still PASS.
4. **Entry-point ordering** — if `cli_extraction.main()` ever constructs the repository before migrating, the ordering test must FAIL.
5. **Marker hygiene / regression** — a Docker-needing test must not run in the default profile: the unit profile must stay green with the Docker daemon poisoned.

---

### Task 1: Record the decision (ADR 0014 + expectations amendment)

**Files:**
- Create: `docs/adr/0014-liquibase-test-strategy.md`
- Modify: `docs/expectations/liquibase-schema-migrations.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the normative rules every later task implements; the wording of the "no second source of truth" amendment that Task 2 relies on.

- [ ] **Step 1: Write `docs/adr/0014-liquibase-test-strategy.md`**

Sections: Context (why `uv run pytest` failed: 52 tests required `liquibase` on `PATH`; per-test Liquibase fixtures ran ~48 `docker run`s), Decision, Consequences, Alternatives considered. The Decision must state, verbatim in substance:
- Tests are split by capability: unit (default, hermetic) vs `integration` (requires Docker + the pinned image).
- `uv run pytest` runs unit tests only; `make test-all` runs everything (this is what CI runs); `make test-integration` requires Docker and fails loudly if it is absent.
- The changelog remains the single source of truth; `tests/_schema/expenses.sql` is a **generated** artifact, valid only while `tests/migrations/test_schema_snapshot.py` proves it identical to the changelog output.
- The wrapper is resolved by absolute path (`<repo>/scripts/liquibase`), never via `PATH`.
- A `Makefile` is the single front door (`test`, `test-integration`, `test-all`, `lint`, `behave`, `provision`, `schema-snapshot`).

Alternatives to record and reject: Testcontainers (no `LiquibaseContainer` module exists in testcontainers-python — verified: 52 modules, none named `liquibase`; still needs Docker, still needs a mounted SQLite file + permission handling, and cannot satisfy `main()`'s `subprocess.run(["liquibase", ...])`); committing a hand-written schema; skipping Liquibase-dependent tests silently.

- [ ] **Step 2: Amend `docs/expectations/liquibase-schema-migrations.md`**

Replace the "no second source of truth" bullet with:

> No **hand-authored** schema definition may exist. Test and BDD databases obtain the schema either by running the changelog, or from `tests/_schema/expenses.sql` — a **generated** artifact that `tests/migrations/test_schema_snapshot.py` proves identical to the changelog output. (Deliberate exception: `tests/migrations/test_changelog.py` recreates a **legacy** pre-`deleted_at` schema to prove the upgrade path.)

Add to the happy path:

> `uv run pytest` runs the hermetic unit suite (no Docker, no `liquibase` on `PATH`) and passes. `make test-all` runs unit + integration and passes. `make test-integration` requires Docker and fails loudly with an actionable message when Docker is unavailable.

- [ ] **Step 3: Verify the docs render and reference real paths**

Run: `uvx ruff check` (unaffected) and `grep -n "expenses.sql\|test_schema_snapshot\|make test-all" docs/adr/0014-liquibase-test-strategy.md docs/expectations/liquibase-schema-migrations.md`
Expected: each path referenced exists in this plan and will exist after Task 2.

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0014-liquibase-test-strategy.md docs/expectations/liquibase-schema-migrations.md
git commit -m "docs: ADR 0014 test strategy for Liquibase-owned schema"
```

---

### Task 2: Schema snapshot seam + drift test

**Files:**
- Create: `tests/_schema.py`
- Create: `tests/_schema/expenses.sql` (generated)
- Create: `tests/migrations/test_schema_snapshot.py`
- Modify: `pyproject.toml` (register the `integration` marker only — no `addopts` yet)

**Interfaces:**
- Consumes: `scripts/liquibase` (existing POSIX wrapper), `db/changelog/db.changelog.xml` (existing).
- Produces (used by Tasks 3, 4, 5, 6):
  - `REPO_ROOT: Path`, `LIQUIBASE_WRAPPER: Path`, `CHANGELOG: str`, `SNAPSHOT_PATH: Path`, `LIQUIBASE_IMAGE: str`
  - `docker_available() -> bool`
  - `require_docker() -> None` (raises `RuntimeError` with an actionable message)
  - `migrate_with_liquibase(db_path: Path) -> None`
  - `apply_snapshot(db_path: Path) -> None`
  - `dump_expenses_ddl(db_path: Path) -> str`
  - `render_snapshot() -> str`
  - `write_snapshot() -> None`
  - `main(argv: list[str] | None = None) -> int` (supports `--write`)

- [ ] **Step 1: Write the failing drift test**

`tests/migrations/test_schema_snapshot.py`:

```python
"""The committed schema snapshot must equal the changelog's output (ADR 0014)."""

from __future__ import annotations

import pytest

from tests._schema import SNAPSHOT_PATH, render_snapshot


@pytest.mark.integration
def test_snapshot_matches_changelog() -> None:
    assert SNAPSHOT_PATH.read_text(encoding="utf-8") == render_snapshot()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/migrations/test_schema_snapshot.py -o addopts="" -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests._schema'`.

- [ ] **Step 3: Implement `tests/_schema.py`**

Signatures exactly as in the Interfaces block. Behaviour:
- `REPO_ROOT = Path(__file__).resolve().parents[1]`; `LIQUIBASE_WRAPPER = REPO_ROOT / "scripts" / "liquibase"`; `CHANGELOG = "db/changelog/db.changelog.xml"`; `SNAPSHOT_PATH = REPO_ROOT / "tests" / "_schema" / "expenses.sql"`; `LIQUIBASE_IMAGE = "liquibase/liquibase:4.33.0"`.
- `docker_available()` runs `docker info --format {{.ServerVersion}}` with `check=False` and returns `returncode == 0`.
- `require_docker()` raises `RuntimeError("Docker is required for integration tests; start Docker and run `make provision`.")` when `docker_available()` is false.
- `migrate_with_liquibase(db_path)` calls `require_docker()` then `subprocess.run([str(LIQUIBASE_WRAPPER), "update", f"--url=jdbc:sqlite:{db_path}", f"--changelog-file={CHANGELOG}"], cwd=REPO_ROOT, check=True)`. Absolute wrapper path — **no `PATH` lookup**.
- `apply_snapshot(db_path)` runs `sqlite3.connect(db_path).executescript(SNAPSHOT_PATH.read_text())`.
- `dump_expenses_ddl(db_path)` returns the `sqlite_master.sql` for table `expenses`, `.strip()`, trailing `;` removed, plus `";\n"`; raise `RuntimeError` if absent.
- `render_snapshot()` = `require_docker()` → migrate a throwaway DB in a `tempfile.TemporaryDirectory()` → `dump_expenses_ddl`.
- `write_snapshot()` writes `render_snapshot()` to `SNAPSHOT_PATH` (creating parent dirs).
- `main(argv)` parses `--write` with `argparse`; `if __name__ == "__main__": raise SystemExit(main())`.

- [ ] **Step 4: Generate the artifact**

Run: `uv run python -m tests._schema --write && cat tests/_schema/expenses.sql`
Expected: a `CREATE TABLE ... expenses (...)` statement with all 10 columns (`id, amount, currency, merchant, date, category, user_id, receipt_photo_id, created_at, deleted_at`).

- [ ] **Step 5: Run the drift test to verify it passes**

Run: `uv run pytest tests/migrations/test_schema_snapshot.py -o addopts="" -v`
Expected: PASS.

- [ ] **Step 6: Prove the drift test actually bites (Review Focus #1)**

Run: `printf '\n-- tamper\n' >> tests/_schema/expenses.sql && uv run pytest tests/migrations/test_schema_snapshot.py -o addopts="" -q; git checkout -- tests/_schema/expenses.sql`
Expected: FAIL while tampered; restored afterwards (`git status --short` clean for that path).

- [ ] **Step 7: Register the `integration` marker**

In `pyproject.toml` under `[tool.pytest.ini_options]` add only:

```toml
markers = [
    "integration: requires Docker and the pinned Liquibase image (liquibase/liquibase:4.33.0)",
]
```

- [ ] **Step 8: Commit**

```bash
git add tests/_schema.py tests/_schema/expenses.sql tests/migrations/test_schema_snapshot.py pyproject.toml
git commit -m "test: generated schema snapshot with changelog drift guard"
```

---

### Task 3: Consolidate repository fixtures onto the snapshot

**Files:**
- Modify: `tests/conftest.py` (remove the dead `migrated_database` fixture; add `snapshot_db` and `repo`)
- Modify: `tests/adapters/out/test_sqlite_repository.py:20-42` and the 9 call sites at lines 302-596
- Modify: `tests/adapters/out/test_sqlite_repository_logging.py:33-54` and the 6 call sites at lines 68-203

**Interfaces:**
- Consumes: `apply_snapshot` from Task 2.
- Produces: `snapshot_db: str` (function-scoped fixture) and `repo: SqliteExpenseRepository` (function-scoped fixture), used by Tasks 4 and 5.

- [ ] **Step 1: Write the failing test**

Add to `tests/adapters/out/test_sqlite_repository.py`:

```python
def test_repository_fixture_needs_no_liquibase(snapshot_db: str) -> None:
    """The repository fixture builds its DB from the snapshot, not from Liquibase."""
    from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

    repo = SqliteExpenseRepository(snapshot_db)
    assert repo.get_by_user_and_month(user_id=1, year=2026, month=1) == []
```

Run: `uv run pytest tests/adapters/out/test_sqlite_repository.py::test_repository_fixture_needs_no_liquibase -o addopts="" -q`
Expected: FAIL — fixture `snapshot_db` not found.

- [ ] **Step 2: Add the fixtures to `tests/conftest.py`**

```python
from tests._schema import apply_snapshot


@pytest.fixture
def snapshot_db(tmp_path: Path) -> str:
    """A fresh database carrying the generated schema snapshot (no Docker)."""
    db = tmp_path / "expenses.db"
    apply_snapshot(db)
    return str(db)


@pytest.fixture
def repo(snapshot_db: str) -> "SqliteExpenseRepository":
    from expense_report.adapters.out.sqlite_repository import SqliteExpenseRepository

    return SqliteExpenseRepository(snapshot_db)
```

Delete the unused `migrated_database` fixture (lines 22-38) and its now-unused `subprocess` import if nothing else uses it.

- [ ] **Step 3: Replace the duplicated helpers in the two repository test modules**

- Delete the local `migrated_db()` function and the local `repo` fixture from both files.
- Replace every `SqliteExpenseRepository(migrated_db())` with `SqliteExpenseRepository(snapshot_db)` (or use the shared `repo` fixture where the test already takes a `repo` parameter), adding `snapshot_db: str` to those test signatures.
- Remove the now-unused `subprocess`, `tempfile`, and `Path` imports if nothing else uses them.

- [ ] **Step 4: Run both modules and confirm no Liquibase invocation**

Run: `DOCKER_HOST=tcp://127.0.0.1:1 uv run pytest tests/adapters/out -o addopts="" -q`
Expected: PASS. (Poisoning `DOCKER_HOST` means any accidental `docker run` would fail — Review Focus #3/#5.)

- [ ] **Step 5: Confirm no `liquibase` reference remains in these modules**

Run: `grep -rn "liquibase\|migrated_db" tests/adapters/out/ ; echo "exit=$?"`
Expected: no matches (`exit=1`).

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/adapters/out/test_sqlite_repository.py tests/adapters/out/test_sqlite_repository_logging.py
git commit -m "test: build repository fixtures from the schema snapshot"
```

---

### Task 4: CLI migration seam + hermetic CLI tests

**Files:**
- Modify: `src/expense_report/adapters/inbound/cli_extraction.py`
- Create: `tests/adapters/inbound/test_cli_migration_ordering.py`
- Modify: `tests/adapters/inbound/test_cli_extraction.py`

**Interfaces:**
- Consumes: `snapshot_db` from Task 3.
- Produces: `ensure_database_migrated(db_path: str) -> None` in `cli_extraction` (the seam later tests stub).

- [ ] **Step 1: Write the failing ordering test**

`tests/adapters/inbound/test_cli_migration_ordering.py`:

```python
"""main() must migrate the database before constructing the repository (ADR 0013)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_main_migrates_before_opening_the_database() -> None:
    order: list[str] = []

    with (
        patch(
            "expense_report.adapters.inbound.cli_extraction.ensure_database_migrated",
            side_effect=lambda db_path: order.append("migrate"),
        ),
        patch(
            "expense_report.adapters.out.sqlite_repository.SqliteExpenseRepository",
            side_effect=lambda db_path: order.append("open") or MagicMock(),
        ),
        patch("expense_report.adapters.out.dspy_extraction.DspyExtractionAdapter"),
        patch("sys.argv", ["expense-extract", "extract-from-text", "coffee 3.50 eur"]),
    ):
        from expense_report.adapters.inbound.cli_extraction import main

        main()

    assert order == ["migrate", "open"]
```

Run: `uv run pytest tests/adapters/inbound/test_cli_migration_ordering.py -q`
Expected: FAIL — `AttributeError: ... does not have the attribute 'ensure_database_migrated'`.

- [ ] **Step 2: Implement the seam in `cli_extraction.py`**

Add above `main()`:

```python
def ensure_database_migrated(db_path: str) -> None:
    """Run `liquibase update` so the schema is current before the DB is opened (ADR 0013)."""
    repo_root = Path(__file__).resolve().parents[4]
    subprocess.run(
        [
            "liquibase",
            "update",
            f"--url=jdbc:sqlite:{db_path}",
            "--changelog-file=db/changelog/db.changelog.xml",
        ],
        cwd=repo_root,
        check=True,
    )
```

Replace the inline `repo_root = ...` + `subprocess.run(...)` block inside `main()` with `ensure_database_migrated(args.db)`.

- [ ] **Step 3: Run the ordering test to verify it passes**

Run: `uv run pytest tests/adapters/inbound/test_cli_migration_ordering.py -q`
Expected: PASS.

- [ ] **Step 4: Prove the ordering test bites (Review Focus #4)**

Temporarily move the `ensure_database_migrated(args.db)` call to after `repo = SqliteExpenseRepository(args.db)`, run the test, confirm FAIL (`order == ["open", "migrate"]`), then restore.
Run: `uv run pytest tests/adapters/inbound/test_cli_migration_ordering.py -q`

- [ ] **Step 5: Make the CLI test module hermetic**

In `tests/adapters/inbound/test_cli_extraction.py`:
- Add a module-level autouse fixture:

```python
@pytest.fixture(autouse=True)
def _stub_real_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "expense_report.adapters.inbound.cli_extraction.ensure_database_migrated",
        lambda db_path: None,
        raising=True,
    )
```

- For the three tests that use a real repository (`test_text_flow_prints_result_and_saves`, `test_image_flow_saves_to_database`, `test_pdf_flow_prints_result_and_saves`), add `snapshot_db: str` to the signature and pass `--db snapshot_db` instead of a `tmp_path` database.

- [ ] **Step 6: Run the whole CLI module with Docker poisoned (Review Focus #3)**

Run: `DOCKER_HOST=tcp://127.0.0.1:1 uv run pytest tests/adapters/inbound/test_cli_extraction.py -o addopts="" -q`
Expected: PASS (14 tests), no Docker access.

- [ ] **Step 7: Commit**

```bash
git add src/expense_report/adapters/inbound/cli_extraction.py tests/adapters/inbound/test_cli_extraction.py tests/adapters/inbound/test_cli_migration_ordering.py
git commit -m "refactor(cli): name the migration step and decouple CLI tests from Docker"
```

---

### Task 5: Unit-by-default profile

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]` — add `addopts`)
- Modify: `tests/migrations/test_changelog.py` (mark integration)

**Interfaces:**
- Consumes: the `integration` marker (Task 2), `snapshot_db` (Task 3), the CLI seam (Task 4).
- Produces: the profile contract (`uv run pytest` = unit only; `uv run pytest -o addopts="" -m integration` = integration) that the deferred `Makefile` will later encode.

- [ ] **Step 1: Write the failing test**

Add `tests/migrations/test_pytest_profile.py`:

```python
"""The default pytest profile is hermetic; integration is opt-in (ADR 0014)."""

from __future__ import annotations

import subprocess


def test_default_profile_deselects_integration() -> None:
    result = subprocess.run(
        ["uv", "run", "pytest", "-m", "", "--collect-only", "-q"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
```

Run: `uv run pytest tests/migrations/test_pytest_profile.py -q`
Expected: PASS (guards the profile switch is documented/possible); the behavioural check is Step 3.

- [ ] **Step 2: Add the default filter**

In `pyproject.toml`:

```toml
addopts = "--strict-markers -m 'not integration'"
```

- [ ] **Step 3: Verify the profiles**

Run: `uv run pytest -q`
Expected: PASS, and the summary shows integration tests **deselected**.

Run: `uv run pytest -o addopts="" -m integration -q`
Expected: the changelog tests + `test_snapshot_matches_changelog` run and PASS (Docker required).

> **BLOCKER — must be resolved before this step is committed.** Flipping the default to unit-only changes what the *existing* CI command (`uv run pytest --cov=expense_report`) runs: it would silently stop running the changelog tests and the snapshot drift test, so the drift guard would no longer protect the snapshot. This step therefore requires **either** (i) a one-line CI change (`uv run pytest -o addopts="" --cov=expense_report`) — an `Ask First` workflow edit — **or** (ii) deferring this task (keep `uv run pytest` running everything; the unit profile remains available as `uv run pytest -m 'not integration'`). Decision owner: human partner.

- [ ] **Step 4: Mark `tests/migrations/test_changelog.py`**

Decorate all three tests (or the module) with `@pytest.mark.integration` and add `import pytest` if missing.

- [ ] **Step 5: Prove the profile is hermetic (Review Focus #3)**

Run: `DOCKER_HOST=tcp://127.0.0.1:1 uv run pytest -q`
Expected: PASS — unit suite needs no Docker; integration tests deselected.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml tests/migrations/test_changelog.py tests/migrations/test_pytest_profile.py
git commit -m "test: run unit tests by default, integration on demand"
```

---

## Deferred to a later increment (NOT in this plan)

Agreed with the human partner to keep the `Makefile` out of this increment. Deferred together with it, because they are all part of the same "single front door" decision:

- `Makefile` with `test` / `test-integration` / `test-all` / `lint` / `behave` / `provision` / `schema-snapshot`.
- `make provision` (`docker pull liquibase/liquibase:4.33.0`) as an explicit provisioning step.
- Rewiring `.github/workflows/ci.yml` to the Makefile (drop the `sudo cp scripts/liquibase /usr/local/bin/liquibase` lines; run the full profile).
- `Makefile`-based instructions in `README.md`.

**Exception — not deferrable:** the CI invocation must still run the integration tests, otherwise the Task 2 drift guard stops protecting the snapshot. Whether that lands as a one-line CI edit now or as part of the deferred increment is the open decision recorded in Task 5 Step 3.

---

## Self-Review

**1. Spec coverage**
- Split unit vs integration → Tasks 2 (marker), 5 (profile). ✔
- Default profile hermetic → Task 5 Step 5. ✔
- No `PATH` dependence → Task 2 (`migrate_with_liquibase` absolute path), Task 3 Step 4, Task 4 Step 6. ✔
- Reduce integration surface (S2) → Tasks 2–3. ✔
- S1 CLI seam → Task 4. ✔
- Fixture consolidation + dead fixture removal → Task 3. ✔
- Docs: ADR + expectations → Task 1. ✔
- Makefile / provisioning / CI rewiring → **deferred** (see Deferred section). ⏸
- CI still runs integration tests → **open decision**, Task 5 Step 3. ⚠

**2. Step scan** — every step names an exact path, signature, command, or expected result; no "handle edge cases"/"TBD" lines.

**3. Type consistency** — `apply_snapshot`, `render_snapshot`, `migrate_with_liquibase`, `SNAPSHOT_PATH`, `snapshot_db`, `repo`, `ensure_database_migrated` keep the same names/signatures across all tasks.

**4. Review Focus** — #1 → Task 2 Step 6; #2 → Task 2 Step 6 + Task 5 Step 3; #3 → Task 3 Step 4, Task 4 Step 6, Task 5 Step 5; #4 → Task 4 Step 4; #5 → Task 3 Step 4, Task 5 Step 5. All five pinned.

**5. Proportion** — plan is comparable in length to the changes it describes; code appears only where the test's exact assertions or a signature fix a decision.

## Open items flagged for the reviewer

- **OPEN DECISION (Task 5 Step 3):** flipping the default profile to unit-only makes the *existing* CI command (`uv run pytest --cov=expense_report`) run unit tests only, silently disabling the Task 2 drift guard in CI. Resolving it requires either a one-line CI edit — an AGENTS.md `Ask First` workflow change — or deferring Task 5. Not the implementer's call.
- **Task 4 Step 2 changes production code** (`cli_extraction.py`) — a pure extraction, no behaviour change; included because AGENTS.md `Ask First` covers port interfaces, and this is not one.
- `features/environment.py` keeps using the real changelog for BDD (acceptance level), so `uv run behave` remains integration. If BDD should also use the snapshot for speed, that is a follow-up, not part of this plan.
- If the Task 5 flip is **deferred**, `AGENTS.md`'s Test rows stay truthful only while `uv run pytest` keeps running the whole suite; the unit profile is then the opt-in `uv run pytest -m 'not integration'`. If the flip lands, `AGENTS.md`'s Test rows must be updated in the same task.
