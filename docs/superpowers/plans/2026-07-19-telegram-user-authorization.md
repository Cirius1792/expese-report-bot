# Telegram User Authorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram user-ID whitelist so unauthorized users are silently ignored and every unauthorized attempt is appended to a dedicated plain-text audit file.

**Architecture:** Authorization lives in the Telegram inbound adapter layer. A python-telegram-bot `TypeHandler(Update, authorization_guard)` registered with `group=-1` gates every update before existing command, text, photo, report, and correction handlers run. Config loading and unauthorized audit logging stay in a focused inbound adapter module; the domain layer remains free of Telegram, JSON, filesystem, and logging configuration concerns.

**Tech Stack:** Python 3.12+, python-telegram-bot v21 style APIs, stdlib `json`/`pathlib`/`logging`, uv, ruff, ty, pytest, Behave.

## Global Constraints

- No new third-party dependencies.
- Use `AUTHORIZED_USERS_CONFIG_PATH` for the whitelist JSON path.
- Use `UNAUTHORIZED_LOG_PATH` for the unauthorized audit log override.
- If `UNAUTHORIZED_LOG_PATH` is unset, default to `unauthorized.log` in the same directory as `EXPENSE_DB_PATH`.
- Whitelist JSON schema is exactly `{ "authorized_users": ["123456789"] }` with numeric strings only.
- Whitelist is loaded once at startup; config changes require bot restart.
- Authorization is based on `update.effective_user.id`, not chat ID.
- Missing config env var, missing file, or unreadable file starts the bot with an empty authorized set and emits a warning.
- Malformed JSON fails startup.
- Valid JSON with invalid schema starts the bot with an empty authorized set and emits a warning.
- Unauthorized audit file creation/write verification failure fails startup.
- Unauthorized users receive no reply and downstream handlers do not run.
- Unauthorized audit lines follow this shape: `2026-07-19T12:00:00Z user_id=123456789`.
- Domain code must not import Telegram, JSON config loading, filesystem audit logging, or PTB dispatching APIs.
- Before claiming completion, run and paste actual output from `uvx ruff format`, `uvx ruff check`, `uvx ty check`, `uv run pytest`, and `uv run behave`.

---

## File Structure

Create or modify these files:

- Create: `src/expense_report/adapters/inbound/authorization.py`
  - Owns whitelist loading, unauthorized audit file writing, PTB authorization guard creation, and guard registration.
- Modify: `src/expense_report/adapters/inbound/main.py`
  - Wires authorization at startup before normal handler registration.
- Create: `tests/adapters/inbound/test_authorization.py`
  - Unit tests for whitelist loading, audit writing, guard behavior, and guard registration.
- Modify: `tests/adapters/inbound/test_logging_config.py`
  - Updates main startup call-order expectations for authorization wiring.
- Modify: `tests/conftest.py`
  - Adds PTB mocks for `ApplicationHandlerStop` and `TypeHandler`.
- Create: `features/authorization.feature`
  - Behave acceptance feature for authorized and unauthorized free-text interactions.
- Create: `features/steps/authorization_steps.py`
  - Step definitions that run the authorization guard and then the normal text handler only when the guard allows the update.
- Modify: `features/environment.py`
  - Adds PTB mocks for `ApplicationHandlerStop` and `TypeHandler`, plus a per-scenario temp directory for authorization audit logs.
- Create: `docs/expectations/authorization.md`
  - EDD expectation document for the authorization feature.
- Create: `docs/adr/0005-telegram-user-authorization.md`
  - Records the PTB-native `TypeHandler` guard decision.
- Modify: `.env.example`
  - Documents local authorization config variables.
- Modify: `.env.deploy.example`
  - Documents deployment authorization config variables.
- Modify: `README.md`
  - Documents the feature, config schema, startup failure rules, and audit file behavior.
- Create: `authorized-users.example.json`
  - A copyable sample whitelist file with fake numeric-string user IDs.

---

### Task 1: BDD acceptance slice and minimal guard behavior

**Files:**
- Create: `docs/expectations/authorization.md`
- Create: `docs/adr/0005-telegram-user-authorization.md`
- Create: `features/authorization.feature`
- Create: `features/steps/authorization_steps.py`
- Modify: `features/environment.py`
- Modify: `tests/conftest.py`
- Create: `src/expense_report/adapters/inbound/authorization.py`

**Interfaces:**
- Consumes: `features.steps.common_steps.make_telegram_update`, `features.steps.common_steps.get_last_reply`, `expense_report.adapters.inbound.telegram_bot._make_text_handler`.
- Produces:
  - `class UnauthorizedAttemptAudit(log_path: str | Path, clock: Callable[[], datetime] | None = None)`
  - `UnauthorizedAttemptAudit.record(user_id: int) -> None`
  - `def make_authorization_guard(authorized_user_ids: Collection[int], audit: UnauthorizedAttemptAudit) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]`

- [ ] **Step 1: Write the EDD expectations document**

Create `docs/expectations/authorization.md`:

```markdown
# Expectations: Telegram User Authorization

## Happy path

- When a Telegram user's `effective_user.id` is present in the loaded whitelist, the authorization guard allows the update to continue to the existing bot handlers.
- Authorized users can send a free-text expense message and receive a normal bot reply.
- Authorized interactions do not write to `unauthorized.log`.

## Edge cases

- If the whitelist config env var is missing, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the whitelist file is missing or unreadable, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the whitelist file contains malformed JSON, startup fails.
- If the whitelist file contains valid JSON with an invalid schema, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the unauthorized audit file cannot be created or written, startup fails.
- Updates with no `effective_user` are stopped silently and do not write a misleading `user_id` audit line.

## Behaviors that must NOT happen

- Unauthorized users must not receive any bot reply.
- Unauthorized updates must not reach text, photo, command, report, correction, extraction, or persistence handlers.
- The domain layer must not import Telegram, JSON configuration, or filesystem audit logging code.
- The audit file must not contain message text, photo IDs, usernames, chat IDs, credentials, or LLM payloads.
- The whitelist must not authorize numeric JSON values; entries must be numeric strings.

## Evidence mapping

- Behave: `features/authorization.feature` proves the authorized and unauthorized user stories.
- Pytest: `tests/adapters/inbound/test_authorization.py` proves loader, audit writer, guard, and registration edge cases.
- Pytest: `tests/adapters/inbound/test_logging_config.py` proves startup wiring order.
- Full verification: `uvx ruff format`, `uvx ruff check`, `uvx ty check`, `uv run pytest`, and `uv run behave`.
```

- [ ] **Step 2: Write the ADR for the authorization pattern**

Create `docs/adr/0005-telegram-user-authorization.md`:

```markdown
# ADR 0005: Telegram User Authorization Guard

**Date:** 2026-07-19
**Status:** Accepted

## Context

The bot must reject Telegram updates from users that are not present in an operator-managed whitelist. Unauthorized users must be silently ignored, and each unauthorized attempt must be appended to a dedicated plain-text audit file with timestamp and Telegram user ID.

The project uses python-telegram-bot v21 style APIs. Existing handlers are registered for `/start`, `/report`, receipt photos, free-text expenses, and correction replies.

## Decision

Use a python-telegram-bot `TypeHandler(Update, authorization_guard)` registered with `group=-1` as a global authorization gate.

The guard checks `update.effective_user.id` against the loaded whitelist:

- authorized user: return normally so later handler groups can process the update;
- unauthorized user: append one audit line and raise `ApplicationHandlerStop`;
- update with no effective user: raise `ApplicationHandlerStop` without writing an audit line.

## Consequences

- Authorization is centralized and applies to commands, text messages, photos, correction replies, and future Telegram handlers.
- Existing expense handlers stay focused on expense behavior and do not duplicate whitelist checks.
- The domain layer remains independent of Telegram, JSON configuration, and filesystem audit logging.
- Tests must include PTB mocks for `TypeHandler` and `ApplicationHandlerStop` because unit and Behave tests mock the Telegram package boundary.
```

- [ ] **Step 3: Write the Behave feature**

Create `features/authorization.feature`:

```gherkin
Feature: Telegram user authorization
  As the bot owner
  I want only whitelisted Telegram users to interact with the bot
  So that unauthorized users cannot use the expense-report bot

  Background:
    Given the bot is running
    And the extraction service is working
    And the database is empty

  @story-11
  Scenario: Authorized user can send a free-text expense message
    Given the bot authorization whitelist contains my Telegram user ID
    When I send a free-text expense message "coffee 3.50 eur at Central Cafe 2026-07-12" through the authorization gate
    Then the bot should send a reply

  @story-11
  Scenario: Unauthorized user is silently ignored and logged
    Given the bot authorization whitelist does not contain my Telegram user ID
    When I send a free-text expense message "coffee 3.50 eur at Central Cafe 2026-07-12" through the authorization gate
    Then the bot should not send any reply
    And the unauthorized attempts log should contain my Telegram user ID
    And the unauthorized attempts log should contain an ISO-8601 UTC timestamp
```

- [ ] **Step 4: Add Behave step definitions that describe the final behavior**

Create `features/steps/authorization_steps.py`:

```python
"""Step definitions for Telegram authorization feature."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from behave import given, then, when

from expense_report.domain.models import ExtractionResult
from features.steps.common_steps import get_last_reply, make_telegram_update


def _authorization_log_path(context: Any) -> Path:
    path = getattr(context, "unauthorized_log_path", None)
    if path is None:
        path = Path(context.authorization_tempdir.name) / "unauthorized.log"
        context.unauthorized_log_path = path
    return Path(path)


@given("the bot authorization whitelist contains my Telegram user ID")
def step_whitelist_contains_user(context: Any) -> None:
    context.authorized_user_ids = frozenset({context.user_id})
    _authorization_log_path(context)


@given("the bot authorization whitelist does not contain my Telegram user ID")
def step_whitelist_excludes_user(context: Any) -> None:
    context.authorized_user_ids = frozenset({context.user_id + 1})
    _authorization_log_path(context)


@when('I send a free-text expense message "{text}" through the authorization gate')
def step_send_text_through_authorization_gate(context: Any, text: str) -> None:
    from telegram.ext import ApplicationHandlerStop

    from expense_report.adapters.inbound.authorization import (
        UnauthorizedAttemptAudit,
        make_authorization_guard,
    )
    from expense_report.adapters.inbound.telegram_bot import _make_text_handler

    update = make_telegram_update(context, text=text)
    audit = UnauthorizedAttemptAudit(
        _authorization_log_path(context),
        clock=lambda: context.current_datetime.replace(tzinfo=UTC),
    )
    guard = make_authorization_guard(context.authorized_user_ids, audit)

    try:
        asyncio.run(guard(update, MagicMock()))
    except ApplicationHandlerStop:
        context.authorization_stopped = True
        return

    context.authorization_stopped = False
    extraction_adapter = MagicMock()
    extraction_adapter.extract.return_value = ExtractionResult(
        amount=None,
        currency=None,
        merchant=None,
        date=None,
        category=None,
    )
    handler = _make_text_handler(
        extraction_adapter,
        context.repository,
        context.correction_store,
    )
    asyncio.run(handler(update, MagicMock()))


@then("the bot should send a reply")
def step_bot_should_send_reply(context: Any) -> None:
    reply = get_last_reply(context)
    assert reply != "", "Expected authorized user to receive a bot reply"


@then("the bot should not send any reply")
def step_bot_should_not_send_reply(context: Any) -> None:
    reply = get_last_reply(context)
    assert reply == "", f"Expected no reply for unauthorized user, got: {reply}"


@then("the unauthorized attempts log should contain my Telegram user ID")
def step_unauthorized_log_contains_user_id(context: Any) -> None:
    content = _authorization_log_path(context).read_text(encoding="utf-8")
    assert f"user_id={context.user_id}" in content, content


@then("the unauthorized attempts log should contain an ISO-8601 UTC timestamp")
def step_unauthorized_log_contains_iso_timestamp(context: Any) -> None:
    content = _authorization_log_path(context).read_text(encoding="utf-8")
    pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z user_id=\d+$"
    lines = [line for line in content.splitlines() if line.strip()]
    assert any(re.match(pattern, line) for line in lines), content
```

- [ ] **Step 5: Add Telegram test mocks for PTB authorization primitives**

Modify `features/environment.py` after the `mock_ext.MessageHandler = _MagicMock()` assignment:

```python
mock_ext.TypeHandler = _MagicMock()


class _MockApplicationHandlerStop(Exception):
    """Mock PTB ApplicationHandlerStop exception for Behave tests."""


mock_ext.ApplicationHandlerStop = _MockApplicationHandlerStop
```

Modify `tests/conftest.py` after the `mock_ext.MessageHandler = mock_message_handler_cls` assignment:

```python
# telegram.ext.TypeHandler
mock_type_handler_cls = MagicMock()
mock_ext.TypeHandler = mock_type_handler_cls


class _MockApplicationHandlerStop(Exception):
    """Mock PTB ApplicationHandlerStop exception for tests."""


mock_ext.ApplicationHandlerStop = _MockApplicationHandlerStop
```

- [ ] **Step 6: Add Behave temp-directory lifecycle**

Modify `features/environment.py` imports:

```python
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING
```

Add this in `before_scenario` after `context.current_datetime = datetime(2026, 7, 15, 12, 0, 0)`:

```python
    context.authorization_tempdir = TemporaryDirectory()
    context.unauthorized_log_path = Path(context.authorization_tempdir.name) / "unauthorized.log"
```

Add this in `after_scenario` after the repository close block:

```python
    if hasattr(context, "authorization_tempdir"):
        context.authorization_tempdir.cleanup()
```

- [ ] **Step 7: Run the acceptance test and verify it fails before implementation**

Run:

```bash
uv run behave features/authorization.feature
```

Expected result: command exits non-zero and output contains:

```text
ModuleNotFoundError: No module named 'expense_report.adapters.inbound.authorization'
```

- [ ] **Step 8: Implement the minimal guard and audit writer**

Create `src/expense_report/adapters/inbound/authorization.py`:

```python
"""Telegram user authorization helpers for the inbound adapter.

This module owns Telegram-specific authorization, whitelist configuration,
and the dedicated unauthorized-attempt audit file.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection
from datetime import UTC, datetime
from pathlib import Path

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

logger = logging.getLogger(__name__)


class UnauthorizedAttemptAudit:
    """Append unauthorized Telegram user attempts to a plain-text audit file."""

    def __init__(
        self,
        log_path: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_path = Path(log_path)
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        """Return the audit file path."""
        return self._log_path

    def record(self, user_id: int) -> None:
        """Append one unauthorized-attempt line for the given Telegram user ID."""
        with self._log_path.open("a", encoding="utf-8") as file:
            file.write(f"{self._timestamp()} user_id={user_id}\n")

    def _timestamp(self) -> str:
        current = self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_authorization_guard(
    authorized_user_ids: Collection[int],
    audit: UnauthorizedAttemptAudit,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    """Create a PTB callback that stops unauthorized Telegram updates."""
    authorized = frozenset(authorized_user_ids)

    async def authorization_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None:
            logger.debug("Stopping Telegram update with no effective user")
            raise ApplicationHandlerStop

        user_id = int(update.effective_user.id)
        if user_id in authorized:
            return

        audit.record(user_id)
        raise ApplicationHandlerStop

    return authorization_guard
```

- [ ] **Step 9: Run the acceptance test and verify it passes**

Run:

```bash
uv run behave features/authorization.feature
```

Expected result: command exits zero and output includes:

```text
2 scenarios passed, 0 failed
```

- [ ] **Step 10: Run the required quality gate for this implementation change**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
```

Expected result: all five commands exit zero. Preserve the actual command output for the task evidence.

- [ ] **Step 11: Commit the acceptance slice**

```bash
git add docs/expectations/authorization.md docs/adr/0005-telegram-user-authorization.md features/authorization.feature features/steps/authorization_steps.py features/environment.py tests/conftest.py src/expense_report/adapters/inbound/authorization.py
git commit -m "feat: add telegram authorization acceptance slice"
```

---

### Task 2: Whitelist config loader and audit-path hardening

**Files:**
- Create or modify: `tests/adapters/inbound/test_authorization.py`
- Modify: `src/expense_report/adapters/inbound/authorization.py`

**Interfaces:**
- Consumes: `UnauthorizedAttemptAudit` and `make_authorization_guard` from Task 1.
- Produces:
  - `AUTHORIZED_USERS_CONFIG_ENV: str`
  - `UNAUTHORIZED_LOG_ENV: str`
  - `class MalformedAuthorizationConfigError(ValueError)`
  - `def load_authorized_user_ids(config_path: str | None) -> frozenset[int]`
  - `def load_authorized_user_ids_from_env(environ: Mapping[str, str] = os.environ) -> frozenset[int]`
  - `def resolve_unauthorized_log_path(db_path: str, unauthorized_log_path: str | None) -> Path`
  - `UnauthorizedAttemptAudit.verify_writable() -> None`

- [ ] **Step 1: Write failing pytest tests for config loading and audit path behavior**

Create `tests/adapters/inbound/test_authorization.py` with these tests:

```python
"""Tests for Telegram user authorization helpers."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from expense_report.adapters.inbound.authorization import (
    MalformedAuthorizationConfigError,
    UnauthorizedAttemptAudit,
    load_authorized_user_ids,
    load_authorized_user_ids_from_env,
    make_authorization_guard,
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
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/adapters/inbound/test_authorization.py -q
```

Expected result: command exits non-zero and output contains missing names such as:

```text
ImportError
MalformedAuthorizationConfigError
load_authorized_user_ids
```

- [ ] **Step 3: Implement config loading, path resolution, and write verification**

Replace `src/expense_report/adapters/inbound/authorization.py` with this complete module:

```python
"""Telegram user authorization helpers for the inbound adapter.

This module owns Telegram-specific authorization, whitelist configuration,
and the dedicated unauthorized-attempt audit file.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import UTC, datetime
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, TypeHandler

logger = logging.getLogger(__name__)

AUTHORIZED_USERS_CONFIG_ENV = "AUTHORIZED_USERS_CONFIG_PATH"
UNAUTHORIZED_LOG_ENV = "UNAUTHORIZED_LOG_PATH"


class MalformedAuthorizationConfigError(ValueError):
    """Raised when the authorization config file is not valid JSON."""


def load_authorized_user_ids(config_path: str | None) -> frozenset[int]:
    """Load authorized Telegram user IDs from a JSON whitelist file.

    Missing paths and invalid schemas authorize nobody and log a warning.
    Malformed JSON raises because startup must fail for syntactically broken
    config files.
    """
    if not config_path:
        logger.warning(
            "%s is not set; authorizing no Telegram users",
            AUTHORIZED_USERS_CONFIG_ENV,
        )
        return frozenset()

    path = Path(config_path)
    try:
        raw_content = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning(
            "Could not read authorization config %s (%s); authorizing no Telegram users",
            path,
            exc.__class__.__name__,
        )
        return frozenset()

    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise MalformedAuthorizationConfigError(
            f"Malformed authorization config JSON: {path}"
        ) from exc

    if not isinstance(data, dict):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    authorized_users = data.get("authorized_users")
    if not isinstance(authorized_users, list):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    if not all(isinstance(user_id, str) and user_id.isdecimal() for user_id in authorized_users):
        logger.warning(
            "Invalid authorization config schema at %s; authorizing no Telegram users",
            path,
        )
        return frozenset()

    return frozenset(int(user_id) for user_id in authorized_users)


def load_authorized_user_ids_from_env(
    environ: Mapping[str, str] = os.environ,
) -> frozenset[int]:
    """Load authorized Telegram user IDs using AUTHORIZED_USERS_CONFIG_PATH."""
    return load_authorized_user_ids(environ.get(AUTHORIZED_USERS_CONFIG_ENV))


def resolve_unauthorized_log_path(db_path: str, unauthorized_log_path: str | None) -> Path:
    """Resolve the dedicated unauthorized-attempt audit log path."""
    if unauthorized_log_path:
        return Path(unauthorized_log_path)
    return Path(db_path).parent / "unauthorized.log"


class UnauthorizedAttemptAudit:
    """Append unauthorized Telegram user attempts to a plain-text audit file."""

    def __init__(
        self,
        log_path: str | Path,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_path = Path(log_path)
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def path(self) -> Path:
        """Return the audit file path."""
        return self._log_path

    def verify_writable(self) -> None:
        """Create the audit file if possible and fail if it is not writable."""
        if not self._log_path.parent.exists():
            raise OSError(
                f"Unauthorized audit log directory does not exist: {self._log_path.parent}"
            )
        with self._log_path.open("a", encoding="utf-8"):
            pass

    def record(self, user_id: int) -> None:
        """Append one unauthorized-attempt line for the given Telegram user ID."""
        with self._log_path.open("a", encoding="utf-8") as file:
            file.write(f"{self._timestamp()} user_id={user_id}\n")

    def _timestamp(self) -> str:
        current = self._clock()
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def make_authorization_guard(
    authorized_user_ids: Collection[int],
    audit: UnauthorizedAttemptAudit,
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]:
    """Create a PTB callback that stops unauthorized Telegram updates."""
    authorized = frozenset(authorized_user_ids)

    async def authorization_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None:
            logger.debug("Stopping Telegram update with no effective user")
            raise ApplicationHandlerStop

        user_id = int(update.effective_user.id)
        if user_id in authorized:
            return

        audit.record(user_id)
        raise ApplicationHandlerStop

    return authorization_guard


def register_authorization_guard(
    app: Application,
    authorized_user_ids: Collection[int],
    audit: UnauthorizedAttemptAudit,
) -> None:
    """Register the global authorization guard before normal Telegram handlers."""
    app.add_handler(
        TypeHandler(Update, make_authorization_guard(authorized_user_ids, audit)),
        group=-1,
    )
```

- [ ] **Step 4: Run focused tests and verify they pass**

Run:

```bash
uv run pytest tests/adapters/inbound/test_authorization.py -q
```

Expected result: command exits zero and output includes passed tests for `test_load_authorized_user_ids_accepts_numeric_strings`, `test_malformed_json_raises_startup_blocking_error`, and `test_audit_record_writes_utc_iso_line`.

- [ ] **Step 5: Run the required quality gate for this implementation change**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
```

Expected result: all five commands exit zero. Preserve the actual command output for the task evidence.

- [ ] **Step 6: Commit config loader and audit hardening**

```bash
git add tests/adapters/inbound/test_authorization.py src/expense_report/adapters/inbound/authorization.py
git commit -m "feat: load telegram authorization config"
```

---

### Task 3: Guard registration and startup wiring

**Files:**
- Modify: `tests/adapters/inbound/test_authorization.py`
- Modify: `tests/adapters/inbound/test_logging_config.py`
- Modify: `src/expense_report/adapters/inbound/main.py`

**Interfaces:**
- Consumes: `load_authorized_user_ids_from_env`, `resolve_unauthorized_log_path`, `UnauthorizedAttemptAudit`, and `register_authorization_guard` from Task 2.
- Produces: startup wiring that verifies the audit file and registers authorization with `group=-1` before normal handlers.

- [ ] **Step 1: Add failing guard and registration unit tests**

Append these tests to `tests/adapters/inbound/test_authorization.py`:

```python

def _make_update(user_id: int | None) -> MagicMock:
    update = MagicMock()
    if user_id is None:
        update.effective_user = None
    else:
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
    return update


def test_authorization_guard_allows_authorized_user(tmp_path: Path) -> None:
    audit = UnauthorizedAttemptAudit(tmp_path / "unauthorized.log")
    guard = make_authorization_guard({123456789}, audit)

    asyncio.run(guard(_make_update(123456789), MagicMock()))

    assert not audit.path.exists()


def test_authorization_guard_logs_and_stops_unauthorized_user(tmp_path: Path) -> None:
    from telegram.ext import ApplicationHandlerStop

    audit = UnauthorizedAttemptAudit(
        tmp_path / "unauthorized.log",
        clock=lambda: datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC),
    )
    guard = make_authorization_guard({987654321}, audit)

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(guard(_make_update(123456789), MagicMock()))

    assert audit.path.read_text(encoding="utf-8") == "2026-07-19T12:00:00Z user_id=123456789\n"


def test_authorization_guard_stops_no_effective_user_without_audit_line(tmp_path: Path) -> None:
    from telegram.ext import ApplicationHandlerStop

    audit = UnauthorizedAttemptAudit(tmp_path / "unauthorized.log")
    guard = make_authorization_guard({123456789}, audit)

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(guard(_make_update(None), MagicMock()))

    assert not audit.path.exists()


def test_register_authorization_guard_uses_type_handler_group_minus_one(tmp_path: Path) -> None:
    from expense_report.adapters.inbound.authorization import register_authorization_guard

    app = MagicMock()
    audit = UnauthorizedAttemptAudit(tmp_path / "unauthorized.log")

    register_authorization_guard(app, {123456789}, audit)

    _, kwargs = app.add_handler.call_args
    assert kwargs == {"group": -1}
```

- [ ] **Step 2: Update the main startup test to expect authorization wiring**

Modify `tests/adapters/inbound/test_logging_config.py` in `TestMainStartsLogging.test_logging_configured_before_adapters`.

Use this environment decorator:

```python
    @patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": "fake:token",
            "EXPENSE_DB_PATH": "/tmp/expenses.db",
            "UNAUTHORIZED_LOG_PATH": "/tmp/unauthorized.log",
        },
        clear=True,
    )
```

Add these helper functions after `build_repository`:

```python
        def load_authorized_users() -> frozenset[int]:
            call_order.append("load_authorized_users")
            return frozenset({123456789})

        def build_audit(*args: object, **kwargs: object) -> MagicMock:
            call_order.append("audit")
            audit = MagicMock()
            audit.verify_writable.side_effect = lambda: call_order.append("audit_verify")
            return audit

        def register_authorization_guard(*args: object, **kwargs: object) -> None:
            call_order.append("register_authorization_guard")
```

Add these patches inside the `with` block:

```python
            patch.object(
                main_module,
                "load_authorized_user_ids_from_env",
                side_effect=load_authorized_users,
            ),
            patch.object(main_module, "UnauthorizedAttemptAudit", side_effect=build_audit),
            patch.object(
                main_module,
                "register_authorization_guard",
                side_effect=register_authorization_guard,
            ),
```

Change the final assertion to:

```python
        assert call_order == [
            "configure_logging",
            "load_authorized_users",
            "audit",
            "audit_verify",
            "extraction_adapter",
            "repository",
            "application_builder",
            "register_authorization_guard",
            "register_handlers",
            "run_polling",
        ]
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
uv run pytest tests/adapters/inbound/test_authorization.py tests/adapters/inbound/test_logging_config.py -q
```

Expected result: command exits non-zero because `main.py` does not yet import or call authorization wiring functions.

- [ ] **Step 4: Wire authorization in the bot entrypoint**

Modify `src/expense_report/adapters/inbound/main.py` imports.

Replace:

```python
from expense_report.adapters.inbound.telegram_bot import register_handlers
```

with:

```python
from expense_report.adapters.inbound.authorization import (
    UNAUTHORIZED_LOG_ENV,
    UnauthorizedAttemptAudit,
    load_authorized_user_ids_from_env,
    register_authorization_guard,
    resolve_unauthorized_log_path,
)
from expense_report.adapters.inbound.telegram_bot import register_handlers
```

Replace `main()` with:

```python
def main() -> None:
    """Start the Telegram bot."""
    effective_log_level = _configure_logging()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    db_path = os.environ.get("EXPENSE_DB_PATH", "expenses.db")

    logger = logging.getLogger(__name__)
    logger.info(
        "Starting expense report bot (db_path=%s, log_level=%s)",
        db_path,
        effective_log_level,
    )

    authorized_user_ids = load_authorized_user_ids_from_env()
    unauthorized_log_path = resolve_unauthorized_log_path(
        db_path,
        os.environ.get(UNAUTHORIZED_LOG_ENV),
    )
    unauthorized_audit = UnauthorizedAttemptAudit(unauthorized_log_path)
    unauthorized_audit.verify_writable()
    logger.info(
        "Telegram authorization loaded with %s authorized users; unauthorized log=%s",
        len(authorized_user_ids),
        unauthorized_audit.path,
    )

    extraction = DspyExtractionAdapter()
    repository = SqliteExpenseRepository(db_path=db_path)
    correction_store = CorrectionStore()

    app = Application.builder().token(token).build()
    register_authorization_guard(app, authorized_user_ids, unauthorized_audit)
    register_handlers(app, extraction, repository, correction_store)
    logger.info("Bot started, entering polling loop")
    app.run_polling()
```

- [ ] **Step 5: Run focused tests and verify they pass**

Run:

```bash
uv run pytest tests/adapters/inbound/test_authorization.py tests/adapters/inbound/test_logging_config.py -q
```

Expected result: command exits zero and includes all tests passing.

- [ ] **Step 6: Run the required quality gate for this implementation change**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
```

Expected result: all five commands exit zero. Preserve the actual command output for the task evidence.

- [ ] **Step 7: Commit startup wiring**

```bash
git add tests/adapters/inbound/test_authorization.py tests/adapters/inbound/test_logging_config.py src/expense_report/adapters/inbound/main.py
git commit -m "feat: wire telegram authorization guard"
```

---

### Task 4: Runtime documentation and deploy examples

**Files:**
- Modify: `.env.example`
- Modify: `.env.deploy.example`
- Modify: `README.md`
- Create: `authorized-users.example.json`

**Interfaces:**
- Consumes: environment variables and config schema implemented in Tasks 2 and 3.
- Produces: operator-facing documentation that makes secure startup and whitelist setup clear.

- [ ] **Step 1: Add a sample whitelist JSON file**

Create `authorized-users.example.json`:

```json
{
  "authorized_users": ["123456789"]
}
```

- [ ] **Step 2: Update local env example**

Append this block to `.env.example` after the `EXPENSE_DB_PATH` section:

```bash
# Telegram user whitelist JSON. If unset or unreadable, no users are authorized.
# Copy authorized-users.example.json and replace the fake ID with your Telegram user ID.
AUTHORIZED_USERS_CONFIG_PATH=authorized-users.json

# Dedicated unauthorized-attempt audit log.
# Defaults to unauthorized.log in the same directory as EXPENSE_DB_PATH when unset.
# UNAUTHORIZED_LOG_PATH=unauthorized.log
```

- [ ] **Step 3: Update deployment env example**

Append this block to `.env.deploy.example` after the UID/GID section:

```bash
# === Authorization ===
# Store this file in ./data on the host so it is visible as /data/authorized-users.json.
AUTHORIZED_USERS_CONFIG_PATH=/data/authorized-users.json

# Optional. Defaults to /data/unauthorized.log because EXPENSE_DB_PATH defaults to /data/expenses.db in the Docker image.
# UNAUTHORIZED_LOG_PATH=/data/unauthorized.log
```

- [ ] **Step 4: Update README feature list and configuration**

In `README.md`, add this bullet to the feature list:

```markdown
- **User authorization whitelist**: Only Telegram user IDs listed in a JSON config file can interact with the bot; unauthorized attempts are silently ignored and written to `unauthorized.log`
```

In the Configuration section, add this block after `EXPENSE_DB_PATH`:

```bash
# Authorization
AUTHORIZED_USERS_CONFIG_PATH=authorized-users.json      # JSON whitelist of Telegram user IDs
UNAUTHORIZED_LOG_PATH=unauthorized.log                  # optional; defaults beside EXPENSE_DB_PATH
```

Add this subsection below the configuration block:

````markdown
### Telegram user authorization

Create a whitelist JSON file before using the bot:

```json
{
  "authorized_users": ["123456789"]
}
```

Values must be numeric strings. Telegram user IDs that are not listed are silently ignored. Each unauthorized attempt appends one line to the dedicated audit file:

```text
2026-07-19T12:00:00Z user_id=987654321
```

Failure behavior:

- Missing `AUTHORIZED_USERS_CONFIG_PATH`, missing whitelist file, or unreadable whitelist file: the bot starts with no authorized users and logs a warning.
- Malformed JSON: startup fails.
- Valid JSON with invalid schema: the bot starts with no authorized users and logs a warning.
- Unwritable unauthorized audit log: startup fails.
````

- [ ] **Step 5: Run documentation-adjacent verification**

Run:

```bash
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave
```

Expected result: all five commands exit zero. Preserve the actual command output for the task evidence.

- [ ] **Step 6: Commit documentation updates**

```bash
git add .env.example .env.deploy.example README.md authorized-users.example.json
git commit -m "docs: document telegram authorization config"
```

---

### Task 5: Final verification and EDD evidence mapping

**Files:**
- Modify: `docs/expectations/authorization.md` if evidence references need command names or scenario names clarified.

**Interfaces:**
- Consumes: all implementation and documentation from Tasks 1-4.
- Produces: final evidence package for the user with actual command output and expectation mapping.

- [ ] **Step 1: Run the full required verification commands individually**

Run each command separately so the final response can paste exact output:

```bash
uvx ruff format
uvx ruff check
uvx ty check
uv run pytest
uv run behave
```

Expected result: each command exits zero.

- [ ] **Step 2: Capture focused authorization evidence**

Run:

```bash
uv run behave features/authorization.feature
uv run pytest tests/adapters/inbound/test_authorization.py tests/adapters/inbound/test_logging_config.py -q
```

Expected result: both commands exit zero. Preserve the exact output.

- [ ] **Step 3: Inspect the final diff for boundary violations**

Run:

```bash
git diff -- src/expense_report/domain src/expense_report/adapters/inbound tests/adapters/inbound features docs/expectations README.md .env.example .env.deploy.example authorized-users.example.json
```

Expected result:

- No changes under `src/expense_report/domain`.
- Authorization code exists under `src/expense_report/adapters/inbound`.
- Tests and Behave scenarios reference Telegram user authorization, not domain authorization.

- [ ] **Step 4: Commit final evidence-note adjustment if the expectation document changed**

If `docs/expectations/authorization.md` was changed in this task, run:

```bash
git add docs/expectations/authorization.md
git commit -m "docs: finalize authorization expectations"
```

If the expectation document was not changed, run:

```bash
git status --short
```

Expected result: no implementation files remain unstaged except pre-existing unrelated local dotfiles.

- [ ] **Step 5: Final response evidence mapping**

In the final response, include:

````markdown
## Verification output

### `uvx ruff format`

```text
Use the exact output from Step 1.
```

### `uvx ruff check`

```text
Use the exact output from Step 1.
```

### `uvx ty check`

```text
Use the exact output from Step 1.
```

### `uv run pytest`

```text
Use the exact output from Step 1.
```

### `uv run behave`

```text
Use the exact output from Step 1.
```

## Expectations mapped to evidence

- Authorized whitelisted user proceeds: `features/authorization.feature`, scenario "Authorized user can send a free-text expense message".
- Unauthorized user receives no reply: `features/authorization.feature`, scenario "Unauthorized user is silently ignored and logged".
- Unauthorized audit line contains timestamp and user ID: `tests/adapters/inbound/test_authorization.py::test_audit_record_writes_utc_iso_line` and Behave unauthorized scenario.
- Malformed JSON fails startup: `tests/adapters/inbound/test_authorization.py::test_malformed_json_raises_startup_blocking_error`.
- Invalid schema authorizes nobody with warning: `tests/adapters/inbound/test_authorization.py::test_invalid_schema_authorizes_nobody_and_warns`.
- Audit log writability failure blocks startup: `tests/adapters/inbound/test_authorization.py::test_audit_verify_writable_raises_when_parent_is_missing`.
- PTB guard is registered globally before normal handlers: `tests/adapters/inbound/test_authorization.py::test_register_authorization_guard_uses_type_handler_group_minus_one` and `tests/adapters/inbound/test_logging_config.py::TestMainStartsLogging::test_logging_configured_before_adapters`.
- Domain boundary preserved: final diff shows no changes under `src/expense_report/domain`.
````

## Self-review

- Spec coverage: all approved design requirements map to Tasks 1-5.
- Placeholder scan: no placeholder markers remain in the plan.
- Type consistency: `UnauthorizedAttemptAudit`, `MalformedAuthorizationConfigError`, `load_authorized_user_ids`, `load_authorized_user_ids_from_env`, `resolve_unauthorized_log_path`, `make_authorization_guard`, and `register_authorization_guard` use the same names and signatures across tests, implementation, and wiring.
