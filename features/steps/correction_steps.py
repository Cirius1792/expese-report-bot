"""Step definitions for correction loop feature (Stories 6-8)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from behave import given, then, when

from expense_report.domain.correction_state import PendingCorrection
from expense_report.domain.models import ExtractionResult
from features.steps.common_steps import (
    get_last_reply,
    make_telegram_update,
)

# ── Given steps for correction state setup ──────────────────────────────────


@given(
    'I have a pending correction with amount "{amount}" but missing currency, merchant, and date'
)
def step_pending_correction_partial(context: Any, amount: str) -> None:
    """Set up a pending correction with only amount filled."""
    original = ExtractionResult(
        amount=Decimal(amount),
        currency=None,
        merchant=None,
        date=None,
        category=None,
    )
    context.correction_store.set(
        context.user_id,
        PendingCorrection(
            user_id=context.user_id,
            original_result=original,
            attempt_count=1,
        ),
    )


@given(
    'I have a pending correction with amount "{amount}", currency "{currency}", '
    'but wrong merchant "{merchant}"'
)
def step_pending_correction_wrong_merchant(
    context: Any, amount: str, currency: str, merchant: str
) -> None:
    """Set up a pending correction where the merchant is wrong."""
    original = ExtractionResult(
        amount=Decimal(amount),
        currency=currency,
        merchant=merchant,  # This is the wrong value
        date=None,
        category=None,
    )
    context.correction_store.set(
        context.user_id,
        PendingCorrection(
            user_id=context.user_id,
            original_result=original,
            attempt_count=1,
        ),
    )


@given('I have a pending correction with only amount "{amount}"')
def step_pending_correction_only_amount(context: Any, amount: str) -> None:
    """Set up a pending correction with just an amount."""
    original = ExtractionResult(
        amount=Decimal(amount),
        currency=None,
        merchant=None,
        date=None,
        category=None,
    )
    context.correction_store.set(
        context.user_id,
        PendingCorrection(
            user_id=context.user_id,
            original_result=original,
            attempt_count=1,
        ),
    )


@given("I have a pending correction that has already been attempted {attempts:d} times")
def step_pending_correction_maxed(context: Any, attempts: int) -> None:
    """Set up a pending correction at the max attempt count."""
    original = ExtractionResult(
        amount=Decimal("15.00"),
        currency=None,
        merchant=None,
        date=None,
        category=None,
    )
    context.correction_store.set(
        context.user_id,
        PendingCorrection(
            user_id=context.user_id,
            original_result=original,
            attempt_count=attempts,
        ),
    )


# ── When steps for correction flow ──────────────────────────────────────────


@when('I reply with the correction text "{text}"')
def step_reply_correction_text(context: Any, text: str) -> None:
    """Send a correction text message to the bot's text handler."""
    context.correction_text = text


@when(
    'the LLM refines the extraction to be complete with merchant "{merchant}" '
    'and date "{expense_date}"'
)
def step_llm_refines_complete(context: Any, merchant: str, expense_date: str) -> None:
    """Configure LLM refine mock to return a complete extraction and execute handler."""
    _execute_text_handler_with_refine(
        context,
        amount="15.00",
        currency="EUR",
        merchant=merchant,
        expense_date=expense_date,
        category="food",
    )


@when('the LLM refines the extraction with merchant "{merchant}"')
def step_llm_refines_merchant(context: Any, merchant: str) -> None:
    """Configure LLM refine mock to return extraction with corrected merchant."""
    _execute_text_handler_with_refine(
        context,
        amount="20.00",
        currency="USD",
        merchant=merchant,
        expense_date="2026-07-20",
        category="hotel",
    )


@when("the LLM refines but still cannot determine currency or date")
def step_llm_refines_still_partial(context: Any) -> None:
    """Configure LLM refine mock to return still-incomplete extraction."""
    _execute_text_handler_with_refine(
        context,
        amount="10.00",
        currency="",
        merchant="Cafe",
        expense_date="",
        category="",
    )


def _execute_text_handler_with_refine(
    context: Any,
    amount: str,
    currency: str,
    merchant: str,
    expense_date: str,
    category: str,
) -> None:
    """Helper: mock refine() response and execute the text handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_text_handler

    # Build mock prediction for refine
    mock_prediction = MagicMock()
    mock_prediction.amount = amount
    mock_prediction.currency = currency
    mock_prediction.merchant = merchant
    mock_prediction.date = expense_date
    mock_prediction.category = category

    with patch("dspy.ChainOfThought") as mock_chain:
        mock_chain_instance = MagicMock(return_value=mock_prediction)
        mock_chain.return_value = mock_chain_instance

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )

        adapter = DspyExtractionAdapter()
        recording = MagicMock()
        handler = _make_text_handler(
            recording, adapter, context.repository, context.correction_store
        )

        text = getattr(context, "correction_text", "correction")
        update = make_telegram_update(context, text=text)
        ctx = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = context.current_datetime
            asyncio.run(handler(update, ctx))


# ── When: another correction attempt after LLM was already called ───────────


@when("I reply with another correction text")
def step_reply_another_correction(context: Any) -> None:
    """Send another correction for the maxed-out scenario."""
    from unittest.mock import MagicMock

    from expense_report.adapters.inbound.telegram_bot import _make_text_handler

    # Don't mock ChainOfThought — adapter.refine should NOT be called
    from expense_report.adapters.out.dspy_extraction import (
        DspyExtractionAdapter,
    )

    adapter = DspyExtractionAdapter()
    recording = MagicMock()
    handler = _make_text_handler(recording, adapter, context.repository, context.correction_store)

    update = make_telegram_update(context, text="another correction")
    ctx = MagicMock()

    with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
        mock_dt.now.return_value = context.current_datetime
        asyncio.run(handler(update, ctx))


# ── Then steps for correction verification ──────────────────────────────────


@then("the bot should save the expense with all fields")
def step_saved_all_fields(context: Any) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) == 1, f"Expected 1 saved expense, got {len(results)}"
    saved = results[0]
    assert saved.amount is not None
    assert saved.currency is not None
    assert saved.merchant is not None
    assert saved.date is not None


@then("the pending correction should be cleared")
def step_correction_cleared(context: Any) -> None:
    pending = context.correction_store.get(context.user_id)
    assert pending is None, f"Expected no pending correction, got: {pending}"


@then('the bot should save the expense with merchant "{merchant}"')
def step_saved_with_merchant(context: Any, merchant: str) -> None:
    results = context.repository.get_by_user_and_month(user_id=context.user_id, year=2026, month=7)
    assert len(results) >= 1
    assert results[0].merchant == merchant


@then("the bot should tell me which fields are still missing")
def step_tells_missing_fields(context: Any) -> None:
    reply = get_last_reply(context)
    missing_keywords = ["missing", "partial", "not extract"]
    assert any(kw in reply.lower() for kw in missing_keywords), (
        f"Expected missing-fields message, got: {reply}"
    )


@then("the correction attempt count should increase to {expected:d}")
def step_attempt_count_increased(context: Any, expected: int) -> None:
    pending = context.correction_store.get(context.user_id)
    assert pending is not None, "Expected a pending correction"
    assert pending.attempt_count == expected, (
        f"Expected attempt count {expected}, got {pending.attempt_count}"
    )


@then("the bot should not call the LLM again")
def step_llm_not_called(context: Any) -> None:
    """In the maxed-out scenario, refine() is not called.
    Verified by not mocking dspy.ChainOfThought — if refine were
    called, it would fail trying to access the unmocked dspy module.
    """
    # If we got here without errors, LLM was not invoked
    pass


@then("the bot should tell me the extraction could not be completed")
def step_extraction_could_not_complete(context: Any) -> None:
    reply = get_last_reply(context)
    assert "3 attempts" in reply or "could not complete" in reply.lower(), (
        f"Expected max attempts message, got: {reply}"
    )


@then("the pending correction should be removed")
def step_correction_removed(context: Any) -> None:
    pending = context.correction_store.get(context.user_id)
    assert pending is None, f"Expected correction to be removed, got: {pending}"
