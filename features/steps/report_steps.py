"""Step definitions for monthly report feature (Stories 9-10)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from behave import given, then, when

from features.steps.common_steps import (
    get_last_document,
    get_last_reply,
    make_telegram_update,
    seed_expense,
)

# ── Given steps for seeded expenses ─────────────────────────────────────────


@given("I have recorded the following expenses this month:")
def step_seed_expenses_table(context: Any) -> None:
    """Seed multiple expenses from a Gherkin data table."""
    for row in context.table:
        seed_expense(
            context,
            user_id=context.user_id,
            amount=row["amount"],
            currency=row["currency"],
            merchant=row["merchant"],
            expense_date=row["date"],
            category=row.get("category"),
        )


@given("I have no expenses recorded this month")
def step_no_expenses(context: Any) -> None:
    """Ensure the database is empty for the current user/period."""
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) == 0


@given('user {user_id:d} has recorded an expense of {amount} {currency} at "{merchant}"')
def step_other_user_expense(
    context: Any, user_id: int, amount: str, currency: str, merchant: str
) -> None:
    """Seed an expense for a specific user (for multi-user isolation tests)."""
    seed_expense(
        context,
        user_id=user_id,
        amount=amount,
        currency=currency,
        merchant=merchant,
        expense_date="2026-07-15",
    )


# ── When steps ──────────────────────────────────────────────────────────────


@when("user {user_id:d} requests /report")
def step_user_requests_report(context: Any, user_id: int) -> None:
    """Run the /report handler for a specific user."""
    from expense_report.adapters.inbound.telegram_bot import _make_report_handler

    handler = _make_report_handler(context.repository)
    update = make_telegram_update(context, user_id=user_id, text="/report")
    ctx = MagicMock()

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))

    # Capture CSV content for later assertions
    doc = get_last_document(context)
    if doc is not None:
        context._csv_content = doc[1]


# ── Then steps ──────────────────────────────────────────────────────────────


@then('the bot should send a CSV file named "{filename}"')
def step_csv_file_sent(context: Any, filename: str) -> None:
    doc = get_last_document(context)
    assert doc is not None, "Expected a CSV document, but none was sent"
    name, content = doc
    assert name == filename, f"Expected filename {filename}, got {name}"
    context._csv_content = content


@then("the CSV should contain {count:d} expense rows")
def step_csv_row_count(context: Any, count: int) -> None:
    csv_content = getattr(context, "_csv_content", b"")
    text = csv_content.decode("utf-8") if isinstance(csv_content, bytes) else csv_content
    lines = [line for line in text.strip().split("\n") if line.strip()]
    # Subtract header line
    data_rows = lines[1:] if len(lines) > 0 else []
    assert len(data_rows) == count, (
        f"Expected {count} data rows, got {len(data_rows)}. Lines: {lines}"
    )


@then('the first row should contain "{text}"')
def step_first_row_contains(context: Any, text: str) -> None:
    csv_content = getattr(context, "_csv_content", b"")
    text_content = csv_content.decode("utf-8") if isinstance(csv_content, bytes) else csv_content
    lines = text_content.strip().split("\n")
    assert len(lines) >= 1, "CSV has no content"
    data_rows = lines[1:]
    assert len(data_rows) >= 1, "CSV has no data rows"
    assert text in data_rows[0], f'Expected "{text}" in first row "{data_rows[0]}"'


@then('the bot should reply with "Generated report with {count:d} expenses"')
def step_generated_report_count(context: Any, count: int) -> None:
    reply = get_last_reply(context)
    assert f"Generated report with {count} expenses" in reply, (
        f"Expected count message, got: {reply}"
    )


@then('the bot should reply with "No expenses recorded for {period}"')
def step_no_expenses_message(context: Any, period: str) -> None:
    reply = get_last_reply(context)
    assert f"No expenses recorded for {period}" in reply, (
        f"Expected empty message for {period}, got: {reply}"
    )


@then("the bot should not send any file")
def step_no_file_sent(context: Any) -> None:
    doc = get_last_document(context)
    assert doc is None, f"Expected no file, but got: {doc}"


@then('the CSV should contain "{text}"')
def step_csv_contains(context: Any, text: str) -> None:
    csv_content = getattr(context, "_csv_content", b"")
    text_content = csv_content.decode("utf-8") if isinstance(csv_content, bytes) else csv_content
    assert text in text_content, f'Expected CSV to contain "{text}", got: {text_content}'


@then('the CSV should not contain "{text}"')
def step_csv_not_contains(context: Any, text: str) -> None:
    csv_content = getattr(context, "_csv_content", b"")
    text_content = csv_content.decode("utf-8") if isinstance(csv_content, bytes) else csv_content
    assert text not in text_content, f'CSV should not contain "{text}", got: {text_content}'
