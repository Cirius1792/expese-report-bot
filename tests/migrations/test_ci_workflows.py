"""Guard rails for the CI test contract (ADR 0014).

The suite is split by capability: a hermetic unit profile (``uv run pytest``)
and an integration profile (``uv run pytest -o addopts=""``, needs Docker).
Both the CI workflow and the release workflow must run the *full* profile — a
bare ``uv run pytest`` silently drops the integration tests and the snapshot
drift guard. These tests pin that wiring and keep a single caller-facing
contract (the reusable tests workflow) from drifting.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
REUSABLE_WORKFLOW = "./.github/workflows/tests.yml"
LIQUIBASE_IMAGE = "liquibase/liquibase:4.33.0"
FULL_PROFILE_COMMAND = 'uv run pytest -o addopts=""'
_CALLERS = ("ci.yml", "release.yml", "tests.yml")


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_reusable_workflow_runs_full_pytest_profile() -> None:
    assert FULL_PROFILE_COMMAND in _read("tests.yml")


def test_reusable_workflow_keeps_marker_validation() -> None:
    """`-o addopts=""` drops the project's `--strict-markers`; re-add it."""
    workflow = _read("tests.yml")
    assert f"{FULL_PROFILE_COMMAND} --strict-markers" in workflow


def test_reusable_workflow_runs_bdd() -> None:
    assert "uv run behave" in _read("tests.yml")


def test_reusable_workflow_restricts_token_permissions() -> None:
    """The workflow runs untrusted PR code, so the token must be read-only."""
    workflow = _read("tests.yml")
    assert "permissions:" in workflow
    assert "contents: read" in workflow


def test_callers_reduce_test_job_permissions() -> None:
    """The callers must not silently grant the default (often write) token."""
    for name in ("ci.yml", "release.yml"):
        assert "permissions:" in _read(name), name
        assert "contents: read" in _read(name), name


def test_reusable_workflow_enables_uv_cache() -> None:
    """Both jobs install dependencies, so both must cache the uv download."""
    assert _read("tests.yml").count("enable-cache: true") == 2


def test_reusable_workflow_bounds_job_runtimes() -> None:
    """A hung pytest/behave/docker step must not occupy a runner indefinitely."""
    assert _read("tests.yml").count("timeout-minutes:") == 2


def test_ci_cancels_superseded_test_runs() -> None:
    ci = _read("ci.yml")
    assert "concurrency:" in ci
    assert "cancel-in-progress: true" in ci


def test_reusable_workflow_pulls_pinned_image() -> None:
    assert f"docker pull {LIQUIBASE_IMAGE}" in _read("tests.yml")


def test_ci_calls_reusable_workflow() -> None:
    assert REUSABLE_WORKFLOW in _read("ci.yml")


def test_release_calls_reusable_workflow() -> None:
    assert REUSABLE_WORKFLOW in _read("release.yml")


def test_no_workflow_runs_bare_pytest() -> None:
    """A bare ``uv run pytest`` silently drops the integration profile (ADR 0014)."""
    for name in _CALLERS:
        for line in _read(name).splitlines():
            if line.lstrip().startswith("#"):
                continue
            if "uv run pytest" in line:
                assert FULL_PROFILE_COMMAND in line, f"{name}: {line.strip()}"


def test_no_workflow_copies_wrapper_onto_path() -> None:
    for name in _CALLERS:
        workflow = _read(name)
        assert "cp scripts/liquibase" not in workflow, name
        assert "/usr/local/bin/liquibase" not in workflow, name
