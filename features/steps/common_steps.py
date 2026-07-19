"""Common step definitions shared across all feature files.

System boundary mocks (dspy, telegram PTB) are configured here.
Internal collaborators (domain entities, repository, correction store)
are used as real instances from the behave context.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from behave import given, then

from expense_report.domain.models import Expense

# ── Background steps ───────────────────────────────────────────────────────


@given("the LLM extraction service is available")
def step_llm_extraction_available(context: Any) -> None:
    """Ensure environment variables for the LLM are set."""
    os.environ.setdefault("LLM_BASE_URL", "http://mock-llm:8080")
    os.environ.setdefault("LLM_API_KEY", "mock-api-key")
    os.environ.setdefault("LLM_MODEL", "mock-model")


@given("the extraction service is working")
def step_extraction_working(context: Any) -> None:
    """Alias for LLM extraction service availability."""
    step_llm_extraction_available(context)


@given("the database is empty")
def step_database_empty_alias(context: Any) -> None:
    """Alias for 'the expense database is empty'."""
    step_database_empty(context)


@given("the expense database is empty")
def step_database_empty(context: Any) -> None:
    """Ensure no expenses exist in the repository."""
    # Repository is fresh per-scenario via environment.py before_scenario
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) == 0, "Database should start empty"


@given("the bot is running")
def step_bot_running(context: Any) -> None:
    """No-op — the bot handlers are stateless functions, no server needed."""
    pass


# ── Extraction adapter helpers ──────────────────────────────────────────────


def configure_text_prediction(context: Any, **fields: str) -> MagicMock:
    """Configure dspy.ChainOfThought mock to return a prediction with given fields.

    Returns the mock prediction object so callers can add additional attributes.
    """
    mock_prediction = MagicMock()
    for field, value in fields.items():
        setattr(mock_prediction, field, value)
    # Ensure all expected fields exist
    for field in ("amount", "currency", "merchant", "date", "category"):
        if not hasattr(mock_prediction, field):
            setattr(mock_prediction, field, "")
    context.last_prediction = mock_prediction
    return mock_prediction


def configure_image_prediction(
    context: Any,
    amount: str = "",
    currency: str = "",
    merchant: str = "",
    date: str = "",
    category: str = "",
) -> None:
    """Configure OpenAI vision API mock to return a JSON response."""
    mock_client = MagicMock()
    content = (
        "{"
        f'"amount":"{amount}","currency":"{currency}",'
        f'"merchant":"{merchant}","date":"{date}","category":"{category}"'
        "}"
    )
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content=content))]
    mock_client.chat.completions.create.return_value = mock_response
    mock_client.chat.completions.create.return_value = mock_response
    context._openai_client = mock_client
    context._image_prediction_content = content


# ── Telegram mock helpers ───────────────────────────────────────────────────


def make_telegram_update(
    context: Any,
    user_id: int | None = None,
    text: str | None = None,
    photo_file_id: str | None = None,
    command: str | None = None,
) -> MagicMock:
    """Create a mock telegram.Update with the given attributes.

    When text starts with '/', it's treated as a command.
    """
    user_id = user_id or context.user_id
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.reply_document = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id

    if command:
        update.effective_message.text = command
    elif text:
        update.effective_message.text = text

    if photo_file_id:
        mock_photo = MagicMock()
        mock_photo.file_id = photo_file_id
        update.effective_message.photo = [MagicMock(), mock_photo]

    context.telegram_updates.append(update)
    return update


def make_telegram_context(context: Any) -> MagicMock:
    """Create a mock CallbackContext with a get_file returning mock file."""
    ctx = MagicMock()
    mock_file = MagicMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=b"fake-receipt-image")
    ctx.bot.get_file = AsyncMock(return_value=mock_file)
    return ctx


def get_last_reply(context: Any) -> str:
    """Get the last reply text sent by the bot."""
    if not context.telegram_updates:
        return ""
    update = context.telegram_updates[-1]
    if update.effective_message.reply_text.await_count > 0:
        return update.effective_message.reply_text.call_args[0][0]
    return ""


def get_last_document(context: Any) -> tuple[str, bytes] | None:
    """Get the last document (filename, content) sent by the bot."""
    if not context.telegram_updates:
        return None
    update = context.telegram_updates[-1]
    if update.effective_message.reply_document.await_count > 0:
        kwargs = update.effective_message.reply_document.call_args[1]
        bio = kwargs["document"]
        return (kwargs["filename"], bio.getvalue())
    return None


# ── Repository helpers ──────────────────────────────────────────────────────


def seed_expense(
    context: Any,
    user_id: int | None = None,
    amount: str = "10.00",
    currency: str = "EUR",
    merchant: str = "Test Shop",
    expense_date: str = "2026-07-15",
    category: str | None = None,
) -> Expense:
    """Insert a single expense into the test repository."""
    user_id = user_id or context.user_id
    expense = Expense(
        id=None,
        amount=Decimal(amount),
        currency=currency,
        merchant=merchant,
        date=date.fromisoformat(expense_date),
        category=category,
        user_id=user_id,
        receipt_photo_id=None,
        created_at=datetime.fromisoformat(f"{expense_date}T12:00:00"),
    )
    return context.repository.save(expense)


# ── Common assertions ───────────────────────────────────────────────────────


@then("the extraction should be complete")
def step_extraction_complete(context: Any) -> None:
    result = context.extraction_result
    assert result is not None, "No extraction result was set"
    assert result.is_complete is True, f"Expected complete extraction, got: {result}"


@then("the extraction should not be complete")
def step_extraction_not_complete(context: Any) -> None:
    result = context.extraction_result
    assert result is not None, "No extraction result was set"
    assert result.is_complete is False, f"Expected incomplete extraction, got: {result}"


@then('the extracted amount should be "{expected}"')
def step_extracted_amount(context: Any, expected: str) -> None:
    result = context.extraction_result
    assert result is not None
    assert result.amount == Decimal(expected), f"Expected amount {expected}, got {result.amount}"


@then('the extracted currency should be "{expected}"')
def step_extracted_currency(context: Any, expected: str) -> None:
    result = context.extraction_result
    assert result is not None
    assert result.currency == expected, f"Expected currency {expected}, got {result.currency}"


@then('the extracted merchant should be "{expected}"')
def step_extracted_merchant(context: Any, expected: str) -> None:
    result = context.extraction_result
    assert result is not None
    assert result.merchant == expected, f"Expected merchant {expected}, got {result.merchant}"


@then('the extracted date should be "{expected}"')
def step_extracted_date(context: Any, expected: str) -> None:
    result = context.extraction_result
    assert result is not None
    assert result.date == date.fromisoformat(expected), (
        f"Expected date {expected}, got {result.date}"
    )


@then('the extracted category should be "{expected}"')
def step_extracted_category(context: Any, expected: str) -> None:
    result = context.extraction_result
    assert result is not None
    assert result.category == expected, f"Expected category {expected}, got {result.category}"


@then("the expense should be saved to the database")
def step_expense_saved(context: Any) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1, "Expected at least one saved expense"


@then("the database should still be empty")
def step_database_still_empty(context: Any) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) == 0, f"Expected empty database, got {len(results)} expenses"


@then("the expense should be persisted with amount {amount} {currency}")
def step_expense_persisted_amount(context: Any, amount: str, currency: str) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1
    saved = results[0]
    assert saved.amount == Decimal(amount), f"Expected amount {amount}, got {saved.amount}"
    assert saved.currency == currency, f"Expected currency {currency}, got {saved.currency}"


@then('the expense should be persisted with merchant "{merchant}"')
def step_expense_persisted_merchant(context: Any, merchant: str) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1
    assert results[0].merchant == merchant, (
        f"Expected merchant {merchant}, got {results[0].merchant}"
    )


@then("the bot should not save any expense")
def step_no_expense_saved(context: Any) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) == 0, f"Expected no expenses saved, got {len(results)}"


@then('the bot should reply with a confirmation containing "{text}"')
def step_reply_contains(context: Any, text: str) -> None:
    reply = get_last_reply(context)
    assert text in reply, f'Expected "{text}" in reply, got: {reply}'


@then('the saved expense should have amount "{amount}" and currency "{currency}"')
def step_saved_expense_check(context: Any, amount: str, currency: str) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1
    saved = results[0]
    assert saved.amount == Decimal(amount)
    assert saved.currency == currency


@then('the saved expense should have merchant "{merchant}"')
def step_saved_merchant(context: Any, merchant: str) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1
    assert results[0].merchant == merchant
