"""The bot entry point must migrate before it opens the database (ADR 0013)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import expense_report.adapters.inbound.main as bot_main


def _patch_main(monkeypatch: pytest.MonkeyPatch, order: list[str]) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "0:test-token")
    monkeypatch.setattr(bot_main, "_configure_logging", lambda: "INFO")
    monkeypatch.setattr(bot_main, "load_authorized_user_ids_from_env", lambda: set())
    monkeypatch.setattr(
        bot_main, "resolve_unauthorized_log_path", lambda db_path, override=None: "/tmp/audit"
    )
    monkeypatch.setattr(bot_main, "UnauthorizedAttemptAudit", lambda path: MagicMock(path=path))
    monkeypatch.setattr(
        bot_main, "ensure_database_migrated", lambda db_path: order.append("migrate")
    )
    monkeypatch.setattr(
        bot_main,
        "SqliteExpenseRepository",
        lambda db_path: order.append("open") or MagicMock(),
    )
    for name in (
        "DspyExtractionAdapter",
        "CorrectionStore",
        "ExpenseQueryUseCase",
        "SourcePreparationAdapter",
        "ExpenseRecordingUseCase",
        "Application",
        "register_authorization_guard",
        "register_handlers",
        "register_global_error_handler",
    ):
        monkeypatch.setattr(bot_main, name, MagicMock())


def test_main_migrates_before_opening_the_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """`expense-bot` is an entry point, so it must migrate before opening SQLite."""
    order: list[str] = []
    monkeypatch.delenv("EXPENSE_SCHEMA_MIGRATED", raising=False)
    _patch_main(monkeypatch, order)

    bot_main.main()

    assert order == ["migrate", "open"]


def test_main_skips_migration_when_entrypoint_already_migrated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The container entrypoint is the single migrator; no second Liquibase JVM."""
    order: list[str] = []
    monkeypatch.setenv("EXPENSE_SCHEMA_MIGRATED", "1")
    _patch_main(monkeypatch, order)

    bot_main.main()

    assert order == ["open"]
