"""Step definitions for Telegram bot shell feature (Stories 3-4)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from behave import given, then, when

from features.steps.common_steps import (
    get_last_reply,
    make_telegram_context,
    make_telegram_update,
)

# ── Given steps ─────────────────────────────────────────────────────────────


@given("I have a valid receipt photo")
def step_have_valid_receipt(context: Any) -> None:
    """Set up context for a photo message."""
    context.photo_file_id = "photo-abc-123"


@given("I have no pending corrections")
def step_no_pending_corrections(context: Any) -> None:
    """Ensure no pending correction exists for the current user."""
    from expense_report.domain.correction_state import CorrectionStore

    if not hasattr(context, "correction_store"):
        context.correction_store = CorrectionStore()
    # Removal is idempotent
    context.correction_store.remove(context.user_id)
    assert context.correction_store.get(context.user_id) is None


# ── When steps ──────────────────────────────────────────────────────────────


@when("I send the photo to the bot")
@when("I send a receipt photo")
def step_send_photo(context: Any) -> None:
    """Trigger the photo handler. Test configures LLM predictions via subsequent step."""
    # This step sets up the photo handler call but defers prediction setup
    # to the "the LLM extracts" step which should come next in the scenario
    context._photo_sent = True


@when(
    'the LLM extracts amount "{amount}", currency "{currency}", merchant "{merchant}", '
    'date "{expense_date}", and category "{category}"'
)
def step_llm_extracts_photo_complete(
    context: Any,
    amount: str,
    currency: str,
    merchant: str,
    expense_date: str,
    category: str,
) -> None:
    """Configure the image LLM mock and execute the photo handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_photo_handler

    # Mock PIL and OpenAI
    with patch("PIL.Image.open") as mock_image_open:
        mock_img = MagicMock()

        def fake_save(buf: Any, **kwargs: Any) -> str:
            return buf.write(b"fake-jpeg-data")  # type: ignore[func-returns-value]

        mock_img.save.side_effect = fake_save
        mock_image_open.return_value = mock_img

        with patch("expense_report.adapters.out.dspy_extraction.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            content = (
                f'{{"amount":"{amount}","currency":"{currency}",'
                f'"merchant":"{merchant}","date":"{expense_date}","category":"{category}"}}'
            )
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=content))]
            mock_client.chat.completions.create.return_value = mock_response

            # Build mock adapter with real DspyExtractionAdapter
            from expense_report.adapters.out.dspy_extraction import (
                DspyExtractionAdapter,
            )

            adapter = DspyExtractionAdapter()
            handler = _make_photo_handler(adapter, context.repository, context.correction_store)

            update = make_telegram_update(
                context,
                photo_file_id=context.photo_file_id,
            )
            ctx = make_telegram_context(context)

            with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
                mock_dt.now.return_value = context.current_datetime
                asyncio.run(handler(update, ctx))


@when('the LLM extracts only the amount "{amount}" without currency, merchant, or date')
def step_llm_extracts_photo_partial(context: Any, amount: str) -> None:
    """Configure the image LLM mock for a partial extraction and execute the handler."""
    from expense_report.adapters.inbound.telegram_bot import _make_photo_handler

    with patch("PIL.Image.open") as mock_image_open:
        mock_img = MagicMock()

        def fake_save(buf: Any, **kwargs: Any) -> str:
            return buf.write(b"fake-jpeg-data")  # type: ignore[func-returns-value]

        mock_img.save.side_effect = fake_save
        mock_image_open.return_value = mock_img

        with patch("expense_report.adapters.out.dspy_extraction.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client

            content = f'{{"amount":"{amount}","currency":"","merchant":"","date":"","category":""}}'
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=content))]
            mock_client.chat.completions.create.return_value = mock_response

            from expense_report.adapters.out.dspy_extraction import (
                DspyExtractionAdapter,
            )

            adapter = DspyExtractionAdapter()
            handler = _make_photo_handler(adapter, context.repository, context.correction_store)

            update = make_telegram_update(
                context,
                photo_file_id=context.photo_file_id,
            )
            ctx = make_telegram_context(context)

            asyncio.run(handler(update, ctx))


@when('I send the message "{text}"')
def step_send_text_message(context: Any, text: str) -> None:
    """Send a text message to the bot using a mocked adapter.

    The LLM predictions are configured by the calling scenario via
    context._telegram_prediction_overrides.
    """
    from expense_report.adapters.inbound.telegram_bot import _make_text_handler

    pred = getattr(context, "_telegram_prediction_overrides", {})
    mock_prediction = MagicMock()
    mock_prediction.amount = pred.get("amount", "")
    mock_prediction.currency = pred.get("currency", "")
    mock_prediction.merchant = pred.get("merchant", "")
    mock_prediction.date = pred.get("date", "")
    mock_prediction.category = pred.get("category", "")

    with patch("dspy.ChainOfThought") as mock_chain:
        mock_chain_instance = MagicMock(return_value=mock_prediction)
        mock_chain.return_value = mock_chain_instance

        from expense_report.adapters.out.dspy_extraction import (
            DspyExtractionAdapter,
        )
        from expense_report.application.expense_recording import (
            ExpenseRecordingUseCase,
        )

        adapter = DspyExtractionAdapter()
        recording = ExpenseRecordingUseCase(adapter, context.repository)
        handler = _make_text_handler(
            recording, adapter, context.repository, context.correction_store
        )
        update = make_telegram_update(context, text=text)
        ctx = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = context.current_datetime
            asyncio.run(handler(update, ctx))


@given(
    'the LLM extracts amount "{amount}", currency "{currency}", '
    'merchant "{merchant}", date "{expense_date}"'
)
@when(
    'the LLM extracts amount "{amount}", currency "{currency}", '
    'merchant "{merchant}", date "{expense_date}"'
)
def step_llm_extracts_text_complete(
    context: Any,
    amount: str,
    currency: str,
    merchant: str,
    expense_date: str,
) -> None:
    """Configure LLM to return a complete text extraction."""
    context._telegram_prediction_overrides = {
        "amount": amount,
        "currency": currency,
        "merchant": merchant,
        "date": expense_date,
        "category": "",
    }


@when('I send the command "{command}"')
def step_send_command(context: Any, command: str) -> None:
    """Send a bot command to the appropriate handler."""
    from expense_report.adapters.inbound.telegram_bot import (
        _handle_start,
        _make_delete_handler,
        _make_list_handler,
        _make_report_handler,
    )

    update = make_telegram_update(context, text=command)

    if command == "/start":
        handler = _handle_start
        ctx = MagicMock()
        asyncio.run(handler(update, ctx))

    elif command == "/report":
        handler = _make_report_handler(context.repository)
        ctx = MagicMock()
        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = context.current_datetime
            asyncio.run(handler(update, ctx))

    elif command == "/list":
        handler = _make_list_handler(context.repository)
        ctx = MagicMock()
        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = context.current_datetime
            asyncio.run(handler(update, ctx))
        context._list_message_text = update.effective_message.reply_text.call_args[0][0]
        context._list_markup = update.effective_message.reply_text.call_args[1].get("reply_markup")

    elif command.startswith("/delete"):
        handler = _make_delete_handler(context.repository)
        ctx = MagicMock()
        asyncio.run(handler(update, ctx))
        context._last_delete_reply = update.effective_message.reply_text.call_args[0][0]


# ── Then steps ──────────────────────────────────────────────────────────────


@then("the bot should reply with a welcome message")
def step_welcome_message(context: Any) -> None:
    reply = get_last_reply(context)
    assert len(reply) > 0, "Expected a welcome message"
    assert "Welcome" in reply or "expense" in reply, f"Unexpected reply: {reply}"


@then('the welcome message should mention "{text}"')
def step_welcome_contains(context: Any, text: str) -> None:
    reply = get_last_reply(context)
    assert text.lower() in reply.lower(), f'Expected "{text}" in welcome message, got: {reply}'


@then("the bot should ask for missing fields")
def step_asks_missing_fields(context: Any) -> None:
    reply = get_last_reply(context)
    assert "partial" in reply.lower() or "missing" in reply.lower(), (
        f"Expected missing fields prompt, got: {reply}"
    )


@then('the missing fields should include "{field1}", "{field2}", and "{field3}"')
def step_missing_fields_include(context: Any, field1: str, field2: str, field3: str) -> None:
    reply = get_last_reply(context)
    for field in (field1, field2, field3):
        assert field in reply, f'Expected "{field}" in missing fields, got: {reply}'


@then("the pending correction should be stored for my user")
def step_pending_correction_stored(context: Any) -> None:
    pending = context.correction_store.get(context.user_id)
    assert pending is not None, "Expected a pending correction"
    assert pending.user_id == context.user_id
    assert pending.attempt_count == 1
