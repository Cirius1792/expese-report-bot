"""Step definitions for interactive /list feature (Stories 11-16)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from behave import given, then, when

# ── Given steps ────────────────────────────────────────────────────────────


@given("the following expenses exist:")
def step_seed_expenses_from_table(context: Any) -> None:
    """Seed multiple expenses from a Gherkin data table.

    Supports optional user_id column for multi-user scenarios.
    """
    from datetime import date, datetime
    from decimal import Decimal

    from expense_report.domain.models import Expense

    for row in context.table:
        user_id = int(row.get("user_id", context.user_id))
        expense = Expense(
            id=None,
            amount=Decimal(row["amount"]),
            currency=row["currency"],
            merchant=row["merchant"],
            date=date.fromisoformat(row["date"]),
            category=row.get("category"),
            user_id=user_id,
            receipt_photo_id=None,
            created_at=datetime.fromisoformat(f"{row['date']}T12:00:00"),
        )
        context.repository.save(expense)


@given("the list view for the current month is displayed")
def step_list_view_displayed(context: Any) -> None:
    """Run the /list handler to set up the initial list view state.

    Captures the InlineKeyboardMarkup on context._list_markup for button-tap tests.
    """
    from expense_report.adapters.inbound.telegram_bot import _make_list_handler

    handler = _make_list_handler(context.repository)
    update = _make_callback_ready_update(context)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.effective_message.reply_text.call_args[0][0]
    context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")


# ── When steps ─────────────────────────────────────────────────────────────


@when('user {user_id:d} sends the command "{command}"')
def step_user_sends_command(context: Any, user_id: int, command: str) -> None:
    """Send a command from a specific user."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_handler

    handler = _make_list_handler(context.repository)
    update = _make_callback_ready_update(context, user_id=user_id)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.effective_message.reply_text.call_args[0][0]
    context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")


@when('the user selects month "{month_name}"')
def step_user_selects_month(context: Any, month_name: str) -> None:
    """Find the callback_data for the given month button and invoke the callback handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

    # Find callback_data from the stored markup
    callback_data = _find_button_callback(context._list_markup, month_name)
    assert callback_data is not None, f"Button '{month_name}' not found in keyboard"

    handler = _make_list_callback_handler(context.repository)
    update = _make_callback_query_update(context, callback_data)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.callback_query.edit_message_text.call_args[1]["text"]
    context._list_markup = update.callback_query.edit_message_text.call_args[1].get("reply_markup")


@when('the user selects year "{year}"')
def step_user_selects_year(context: Any, year: str) -> None:
    """Find the callback_data for the given year button and invoke the callback handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

    callback_data = _find_button_callback(context._list_markup, year)
    assert callback_data is not None, f"Button '{year}' not found in keyboard"

    handler = _make_list_callback_handler(context.repository)
    update = _make_callback_query_update(context, callback_data)
    ctx = _make_callback_ready_context(context)

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    context._list_message_text = update.callback_query.edit_message_text.call_args[1]["text"]
    context._list_markup = update.callback_query.edit_message_text.call_args[1].get("reply_markup")


# ── Then steps ─────────────────────────────────────────────────────────────

# IMPORTANT: step_message_user_expenses MUST be defined before
# step_message_shows_month because behave matches the first pattern that fits.
# "message shows expenses for user {user_id:d}" would incorrectly match
# {month_name}="user" {year:d}=123 if ordered after the month variant.


@then("the message shows expenses for user {user_id:d}")
def step_message_user_expenses(context: Any, user_id: int) -> None:
    text = context._list_message_text
    if user_id == 123:
        assert "User 123 Shop" in text, f"Expected User 123 Shop in message, got: {text[:200]}"
        assert "User 456 Shop" not in text, f"User 456 data leaked: {text[:200]}"
    elif user_id == 456:
        assert "User 456 Shop" in text, f"Expected User 456 Shop in message, got: {text[:200]}"
        assert "User 123 Shop" not in text, f"User 123 data leaked: {text[:200]}"


@then("the message shows expenses for {month_name} {year:d}")
def step_message_shows_month(context: Any, month_name: str, year: int) -> None:
    text = context._list_message_text
    assert month_name in text, f"Expected '{month_name}' in message, got: {text[:200]}"
    assert str(year) in text, f"Expected '{year}' in message, got: {text[:200]}"


@then("the message updates to show expenses for {month_name} {year:d}")
def step_message_updates_month(context: Any, month_name: str, year: int) -> None:
    text = context._list_message_text
    assert month_name in text, f"Expected '{month_name}' in updated message, got: {text[:200]}"
    assert str(year) in text, f"Expected '{year}' in updated message, got: {text[:200]}"


@then('the message shows the total "{total}"')
def step_message_shows_total(context: Any, total: str) -> None:
    text = context._list_message_text
    assert total in text, f"Expected total '{total}' in message, got: {text[:200]}"


@then('the message shows the year total "{total}"')
def step_message_shows_year_total(context: Any, total: str) -> None:
    text = context._list_message_text
    assert total in text, f"Expected year total '{total}' in message, got: {text[:200]}"
    assert "Summary" in text, f"Expected 'Summary' in year view, got: {text[:200]}"


@then('the bot shows buttons labeled "{label1}" and "{label2}"')
def step_buttons_labeled_two(context: Any, label1: str, label2: str) -> None:
    all_labels = set(_get_all_button_labels(context._list_markup))
    expected = {label1, label2}
    assert all_labels == expected, f"Expected exactly buttons {expected}, got {all_labels}"


@then('the bot shows a button labeled "{label}"')
def step_button_labeled(context: Any, label: str) -> None:
    all_labels = _get_all_button_labels(context._list_markup)
    assert label in all_labels, f"Expected button '{label}', got buttons: {all_labels}"


@then('the bot does not show a button labeled "{label}"')
def step_no_button_labeled(context: Any, label: str) -> None:
    labels = _get_all_button_labels(context._list_markup)
    assert label not in labels, f"Button '{label}' should not be present, got buttons: {labels}"


@then('the bot shows exactly these buttons: "{labels}"')
def step_buttons_exact_set(context: Any, labels: str) -> None:
    all_labels = set(_get_all_button_labels(context._list_markup))
    expected = set(label.strip() for label in labels.split(","))
    assert all_labels == expected, f"Expected exactly buttons {expected}, got {all_labels}"


@then("the message explains that only months with expenses are shown")
def step_explanation_message(context: Any) -> None:
    text = context._list_message_text
    assert "only months" in text.lower(), f"Expected explanation about months, got: {text[:200]}"


@then("the bot replies with a message that no expenses are recorded")
def step_no_expenses_message(context: Any) -> None:
    text = context._list_message_text
    assert "no" in text.lower() and "expense" in text.lower(), (
        f"Expected no-expenses message, got: {text[:200]}"
    )


@then("the bot does not show any year or month buttons")
def step_no_buttons(context: Any) -> None:
    assert context._list_markup is None or context._list_markup == [], (
        f"Expected no buttons, got: {context._list_markup}"
    )


@then('the bot shows buttons labeled "{l1}", "{l2}", and "{l3}"')
def step_buttons_labeled_three(context: Any, l1: str, l2: str, l3: str) -> None:
    all_labels = set(_get_all_button_labels(context._list_markup))
    expected = {l1, l2, l3}
    assert all_labels == expected, f"Expected exactly buttons {expected}, got {all_labels}"


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_callback_ready_update(context: Any, user_id: int | None = None) -> MagicMock:
    """Create a mock Update that captures reply_text calls."""
    uid = user_id if user_id is not None else context.user_id
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.reply_document = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = uid
    return update


def _make_callback_ready_context(context: Any) -> MagicMock:
    """Create a mock CallbackContext."""
    return MagicMock()


def _make_callback_query_update(context: Any, callback_data: str) -> MagicMock:
    """Create a mock Update with a CallbackQuery for button-tap tests."""
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.from_user = MagicMock()
    query.from_user.id = context.user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    return update


def _get_all_button_labels(markup: Any) -> list[str]:
    """Extract all button text labels from an InlineKeyboardMarkup mock."""
    if markup is None:
        return []
    labels: list[str] = []
    keyboard = markup.inline_keyboard
    for row in keyboard:
        for btn in row:
            labels.append(btn.text)
    return labels


def _find_button_callback(markup: Any, label: str) -> str | None:
    """Find the callback_data for a button with the given label."""
    if markup is None:
        return None
    keyboard = markup.inline_keyboard
    for row in keyboard:
        for btn in row:
            if btn.text == label:
                return btn.callback_data
    return None
