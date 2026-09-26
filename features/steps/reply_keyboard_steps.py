"""Step definitions for the reply keyboard bottom action bar feature (issue #14)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from behave import then, when

from features.steps.common_steps import make_telegram_update


def _build_label_map(context: Any) -> dict[str, Any]:
    """Build the label→handler map via the production builder (issue #14)."""
    from expense_report.adapters.inbound.telegram_bot import (
        _handle_add,
        _handle_remove,
        _handle_start,
        _make_list_handler,
        _make_report_handler,
        build_label_handlers,
    )

    return build_label_handlers(
        start_handler=_handle_start,
        report_handler=_make_report_handler(context.expense_queries),
        list_handler=_make_list_handler(context.expense_queries),
        add_handler=_handle_add,
        remove_handler=_handle_remove,
    )


@when('I press the keyboard button "{label}"')
def step_press_keyboard_button(context: Any, label: str) -> None:
    """Simulate tapping a reply-keyboard button.

    Telegram delivers the button label as a plain text message; the text
    handler is wired with the full label map, exactly like register_handlers.
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
        from expense_report.adapters.out.source_preparation import (
            SourcePreparationAdapter,
        )
        from expense_report.application.expense_recording import (
            ExpenseRecordingUseCase,
        )

        adapter = DspyExtractionAdapter()
        recording = ExpenseRecordingUseCase(
            SourcePreparationAdapter(),
            adapter,
            context.repository,
            context.correction_store,
        )
        handler = _make_text_handler(recording, _build_label_map(context))
        update = make_telegram_update(context, text=label)
        ctx = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = context.current_datetime
            asyncio.run(handler(update, ctx))


@then("the bot shows the reply keyboard")
def step_reply_keyboard_attached(context: Any) -> None:
    """The latest message carries the persistent reply keyboard (issue #14)."""
    from expense_report.adapters.inbound.telegram_bot import REPLY_KEYBOARD

    update = context.telegram_updates[-1]
    calls = update.effective_message.reply_text.call_args_list
    assert calls, "Expected at least one reply"
    last_markup = calls[-1].kwargs.get("reply_markup")
    assert last_markup is REPLY_KEYBOARD, (
        f"Expected the reply keyboard on the last message, got: {last_markup!r}"
    )
