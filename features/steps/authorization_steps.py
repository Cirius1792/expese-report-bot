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
