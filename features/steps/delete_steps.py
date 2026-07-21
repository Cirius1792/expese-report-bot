"""Step definitions for delete saved expenses feature (Stories 17-18)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from behave import given, then, when

# ── When steps ─────────────────────────────────────────────────────────────


@when('user {user_id:d} sends the delete command "{command}"')
def step_delete_user_command(context: Any, user_id: int, command: str) -> None:
    """Send a /delete command from a specific user (user-scoped variant)."""
    from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

    handler = _make_delete_handler(context.repository)
    update = _make_delete_update(context, user_id=user_id, text=command)
    ctx = MagicMock()
    asyncio.run(handler(update, ctx))
    context._last_delete_reply = update.effective_message.reply_text.call_args[0][0]


@when("I send invalid delete commands:")
def step_send_invalid_delete_commands(context: Any) -> None:
    """Send each invalid delete command and collect replies."""
    from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

    handler = _make_delete_handler(context.repository)
    replies: list[str] = []

    for row in context.table:
        cmd = row["command"]
        update = _make_delete_update(context, text=cmd)
        ctx = MagicMock()
        asyncio.run(handler(update, ctx))
        replies.append(update.effective_message.reply_text.call_args[0][0])

    context._invalid_delete_replies = replies


@when("I tap the delete button for expense #{expense_id:d}")
def step_tap_delete_button(context: Any, expense_id: int) -> None:
    """Simulate tapping the delete button callback."""
    from expense_report.adapters.inbound.telegram_bot import _make_delete_callback_handler

    handler = _make_delete_callback_handler(context.repository)
    update = MagicMock()
    query = MagicMock()
    query.data = f"delete:{expense_id}"
    query.from_user = MagicMock()
    query.from_user.id = context.user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.edit_message_caption = AsyncMock()
    query.edit_message_reply_markup = AsyncMock()
    query.message = MagicMock()
    query.message.text = (
        f"Extracted expense:\nExpense #{expense_id}\n"
        f"Amount: 3.50 EUR\nMerchant: Central Cafe\n"
        f"Date: 2026-07-12\nCategory: food\n\nSaved."
    )
    query.message.caption = None
    update.callback_query = query
    callback_ctx = MagicMock()

    asyncio.run(handler(update, callback_ctx))
    if query.edit_message_text.call_count > 0:
        call_kwargs = query.edit_message_text.call_args[1]
        context._edited_text = call_kwargs.get("text", "")
        context._edited_parse_mode = call_kwargs.get("parse_mode")
        context._edited_reply_markup = call_kwargs.get("reply_markup")
    else:
        context._edited_text = ""
        context._edited_parse_mode = None
        context._edited_reply_markup = None


# ── Given steps ────────────────────────────────────────────────────────────


@given("a saved confirmation for expense #{expense_id:d} exists:")
def step_saved_confirmation_exists(context: Any, expense_id: int) -> None:
    """Seed an expense with a specific id (matching the delete button scenario)."""
    from datetime import date, datetime
    from decimal import Decimal

    from expense_report.domain.models import Expense

    for row in context.table:
        expense = Expense(
            id=int(row["id"]),
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            merchant=row["merchant"],
            date=date.fromisoformat(row["date"]),
            category=row.get("category"),
            user_id=context.user_id,
            receipt_photo_id=None,
            created_at=datetime.fromisoformat(f"{row['date']}T12:00:00"),
        )
        context.repository.save(expense)


# ── Then steps ─────────────────────────────────────────────────────────────


@then('the delete reply should be "{text}"')
def step_bot_reply_exact(context: Any, text: str) -> None:
    """Verify the bot's delete reply matches exactly."""
    reply = getattr(context, "_last_delete_reply", "")
    assert reply == text, f"Expected '{text}', got: '{reply}'"


@then("expense #{expense_id:d} should no longer be recorded")
def step_expense_not_recorded(context: Any, expense_id: int) -> None:
    """Verify expense is not retrievable after deletion."""
    result = context.repository.get_by_id(expense_id)
    assert result is None, f"Expected expense #{expense_id} to be deleted"


@then("expense #{expense_id:d} should still be recorded for user {user_id:d}")
def step_expense_still_recorded(context: Any, expense_id: int, user_id: int) -> None:
    """Verify expense still exists (was not deleted due to user scoping)."""
    result = context.repository.get_by_id(expense_id)
    assert result is not None, f"Expected expense #{expense_id} to still exist"
    assert result.user_id == user_id, f"Expected user {user_id}, got user {result.user_id}"


@then('each delete command should reply with "{expected}"')
def step_each_delete_invalid_reply(context: Any, expected: str) -> None:
    """Verify all invalid commands returned the usage message."""
    replies = getattr(context, "_invalid_delete_replies", [])
    assert len(replies) > 0, "No replies collected"
    for i, reply in enumerate(replies):
        assert reply == expected, f"Reply {i}: expected '{expected}', got '{reply}'"


@then('the edited confirmation still contains "{text}"')
def step_edited_contains(context: Any, text: str) -> None:
    """Verify the edited confirmation still has the original text (though struck through)."""
    edited = getattr(context, "_edited_text", "")
    assert text in edited, f"Expected '{text}' in edited text, got: {edited[:200]}"


@then("the edited confirmation shows struck-through expense details")
def step_edited_strikethrough(context: Any) -> None:
    """Verify HTML strikethrough tags are present."""
    edited = getattr(context, "_edited_text", "")
    assert "<s>" in edited, f"Expected <s> tags in edited text, got: {edited[:200]}"
    assert "</s>" in edited, f"Expected </s> in edited text, got: {edited[:200]}"


@then('the edited confirmation includes "{text}"')
def step_edited_includes_text(context: Any, text: str) -> None:
    """Verify the edited confirmation has the given text."""
    edited = getattr(context, "_edited_text", "")
    assert text in edited, f"Expected '{text}' in edited text, got: {edited[:200]}"


@then("the delete button is removed from the edited confirmation")
def step_edited_no_delete_button(context: Any) -> None:
    """Verify the delete button is no longer present."""
    markup = getattr(context, "_edited_reply_markup", None)
    # No reply_markup means no buttons
    if (
        markup is not None
        and hasattr(markup, "inline_keyboard")
        and len(markup.inline_keyboard) > 0
    ):
        # Check if any button is a delete button
        for row in markup.inline_keyboard:
            for btn in row:
                assert "Delete" not in btn.text, f"Delete button still present: {btn.text}"


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_delete_update(context: Any, user_id: int | None = None, text: str = "") -> MagicMock:
    """Create a mock Update for /delete handler tests."""
    uid = user_id if user_id is not None else context.user_id
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = uid
    update.effective_message.text = text
    return update
