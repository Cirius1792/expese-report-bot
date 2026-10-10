"""Executable test for docker-entrypoint.sh (no image build required).

The script hardcodes ``/app`` paths (its container layout). This test runs a
copy with ``/app`` rewritten to a temp directory and stubs ``liquibase`` and the
bot binary, so the entrypoint's own logic — fail-fast guard, migration-then-exec
ordering, and the working directory handed to the bot — is executed for real.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
ENTRYPOINT = REPO_ROOT / "docker-entrypoint.sh"


def _prepare_app(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return (app_dir, patched_entrypoint, log_file)."""
    app = tmp_path / "app"
    (app / "db").mkdir(parents=True)
    bot = app / ".venv" / "bin" / "expense-bot"
    bot.parent.mkdir(parents=True)

    log = tmp_path / "calls.log"
    bindir = tmp_path / "bin"
    bindir.mkdir()

    fake_liquibase = bindir / "liquibase"
    fake_liquibase.write_text(f'#!/bin/sh\necho "migrate:$PWD" >> "{log}"\n')
    fake_liquibase.chmod(0o755)

    bot.write_text(
        f'#!/bin/sh\necho "bot:$PWD migrated=${{EXPENSE_SCHEMA_MIGRATED:-}}" >> "{log}"\n'
    )
    bot.chmod(0o755)

    patched = app / "docker-entrypoint.sh"
    patched.write_text(ENTRYPOINT.read_text(encoding="utf-8").replace("/app", str(app)))
    patched.chmod(0o755)
    return app, patched, log


def _run(
    patched: Path, tmp_path: Path, cwd: Path, **env_overrides: str
) -> subprocess.CompletedProcess[str]:
    bindir = tmp_path / "bin"
    return subprocess.run(
        [str(patched)],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            **env_overrides,
        },
    )


def test_entrypoint_migrates_then_runs_bot_from_workdir(tmp_path: Path) -> None:
    app, patched, log = _prepare_app(tmp_path)

    # The container image sets WORKDIR /app, so the entrypoint runs from there.
    result = _run(patched, tmp_path, cwd=app, EXPENSE_DB_PATH="/tmp/expenses.db")

    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    # Migration runs from /app/db (relative changelog) ...
    assert calls[0] == f"migrate:{app}/db"
    # ... and the bot starts from /app (the image WORKDIR), not /app/db.
    assert calls[1] == f"bot:{app} migrated=1"


def test_entrypoint_fails_fast_on_empty_database_path(tmp_path: Path) -> None:
    app, patched, log = _prepare_app(tmp_path)

    result = _run(patched, tmp_path, cwd=app, EXPENSE_DB_PATH="")

    assert result.returncode == 1
    assert "EXPENSE_DB_PATH must be set" in result.stderr
    assert not log.exists()
