"""Tests for Telegram user authorization helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from expense_report.adapters.inbound.authorization import (
    MalformedAuthorizationConfigError,
    UnauthorizedAttemptAudit,
    load_authorized_user_ids,
    load_authorized_user_ids_from_env,
    resolve_unauthorized_log_path,
)


def test_load_authorized_user_ids_accepts_numeric_strings(tmp_path: Path) -> None:
    config = tmp_path / "authorized-users.json"
    config.write_text('{"authorized_users": ["123456789", "987654321"]}', encoding="utf-8")

    result = load_authorized_user_ids(str(config))

    assert result == frozenset({123456789, 987654321})


def test_missing_config_env_authorizes_nobody_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    result = load_authorized_user_ids_from_env({})

    assert result == frozenset()
    assert "AUTHORIZED_USERS_CONFIG_PATH" in caplog.text


def test_missing_config_file_authorizes_nobody_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING)
    missing_path = tmp_path / "missing.json"

    result = load_authorized_user_ids(str(missing_path))

    assert result == frozenset()
    assert "authorizing no Telegram users" in caplog.text


def test_unreadable_config_file_authorizes_nobody_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    caplog.set_level(logging.WARNING)
    config = tmp_path / "authorized-users.json"
    config.write_text('{"authorized_users": ["123456789"]}', encoding="utf-8")

    def _raise_permission_error(*args: object, **kwargs: object) -> str:
        msg = "Permission denied"
        raise PermissionError(msg)

    monkeypatch.setattr(Path, "read_text", _raise_permission_error)

    result = load_authorized_user_ids(str(config))

    assert result == frozenset()
    assert "Could not read authorization config" in caplog.text


def test_malformed_json_raises_startup_blocking_error(tmp_path: Path) -> None:
    config = tmp_path / "authorized-users.json"
    config.write_text('{"authorized_users": ["123"', encoding="utf-8")

    with pytest.raises(MalformedAuthorizationConfigError):
        load_authorized_user_ids(str(config))


@pytest.mark.parametrize(
    "content",
    [
        "{}",
        '{"authorized_users": "123456789"}',
        '{"authorized_users": [123456789]}',
        '{"authorized_users": ["abc"]}',
        '["123456789"]',
        '{"authorized_users": ["123456789"], "extra": true}',
    ],
)
def test_invalid_schema_authorizes_nobody_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    content: str,
) -> None:
    caplog.set_level(logging.WARNING)
    config = tmp_path / "authorized-users.json"
    config.write_text(content, encoding="utf-8")

    result = load_authorized_user_ids(str(config))

    assert result == frozenset()
    assert "Invalid authorization config schema" in caplog.text


def test_resolve_unauthorized_log_path_uses_override() -> None:
    result = resolve_unauthorized_log_path("/data/expenses.db", "/audit/unauthorized.log")

    assert result == Path("/audit/unauthorized.log")


def test_resolve_unauthorized_log_path_defaults_to_database_directory() -> None:
    result = resolve_unauthorized_log_path("/data/expenses.db", None)

    assert result == Path("/data/unauthorized.log")


def test_audit_record_writes_utc_iso_line(tmp_path: Path) -> None:
    log_path = tmp_path / "unauthorized.log"
    audit = UnauthorizedAttemptAudit(
        log_path,
        clock=lambda: datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC),
    )

    audit.record(123456789)

    assert log_path.read_text(encoding="utf-8") == "2026-07-19T12:00:00Z user_id=123456789\n"


def test_audit_verify_writable_creates_file_when_parent_exists(tmp_path: Path) -> None:
    log_path = tmp_path / "unauthorized.log"
    audit = UnauthorizedAttemptAudit(log_path)

    audit.verify_writable()

    assert log_path.exists()


def test_audit_verify_writable_raises_when_parent_is_missing(tmp_path: Path) -> None:
    log_path = tmp_path / "missing" / "unauthorized.log"
    audit = UnauthorizedAttemptAudit(log_path)

    with pytest.raises(OSError):
        audit.verify_writable()
