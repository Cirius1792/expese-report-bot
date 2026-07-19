"""Telegram bot handlers for expense report bot.

Driving adapter that handles /start, /report, photo, and text messages.
Uses dependency injection for ExtractionPort and ExpenseRepositoryPort.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from expense_report.domain.correction_state import CorrectionStore, PendingCorrection
from expense_report.domain.csv_generator import generate_csv
from expense_report.domain.models import Expense
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort

WELCOME_MESSAGE = """Welcome! I'm your expense report bot.

Send me a photo of a receipt, or describe your expense like "lunch 15 eur".

Commands:
/start - Show this message
/report - Get your monthly expense report as CSV"""


def register_handlers(
    app: Application,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
) -> None:
    """Register all bot command and message handlers."""
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("report", _make_report_handler(repository)))
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            _make_photo_handler(extraction_adapter, repository, correction_store),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _make_text_handler(extraction_adapter, repository, correction_store),
        )
    )


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — send welcome message."""
    if update.effective_message is None:
        return
    await update.effective_message.reply_text(WELCOME_MESSAGE)


def _make_report_handler(
    repository: ExpenseRepositoryPort,
):
    """Factory: create a /report handler bound to the given repository."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            return

        user_id = update.effective_user.id
        now = datetime.now()
        year = now.year
        month = now.month

        expenses = repository.get_by_user_and_month(user_id, year, month)

        if not expenses:
            await update.effective_message.reply_text(
                f"No expenses recorded for {year:04d}-{month:02d}."
            )
            return

        csv_string = generate_csv(expenses)
        filename = f"expenses-{year:04d}-{month:02d}.csv"

        bio = BytesIO(csv_string.encode("utf-8"))
        bio.name = filename

        await update.effective_message.reply_document(document=bio, filename=filename)
        await update.effective_message.reply_text(
            f"📊 Generated report with {len(expenses)} expenses."
        )

    return handler


def _make_photo_handler(
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
):
    """Factory: create a photo handler bound to the given adapters."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            return

        photo = update.effective_message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        result = extraction_adapter.extract(bytes(image_bytes), "image")

        if not result.is_complete:
            correction_store.set(
                update.effective_user.id,
                PendingCorrection(
                    user_id=update.effective_user.id,
                    original_result=result,
                ),
            )

        await _respond_to_extraction(
            update,
            result,
            repository,
            receipt_photo_id=photo.file_id,
        )

    return handler


def _make_text_handler(
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
):
    """Factory: create a text handler bound to the given adapters."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            return

        text = update.effective_message.text
        if text is None:
            return

        user_id = update.effective_user.id
        pending = correction_store.get(user_id)

        if pending is not None:
            # Correction flow: refine with user's correction text
            await _handle_correction(
                update,
                pending,
                text,
                extraction_adapter,
                repository,
                correction_store,
            )
            return

        # No pending correction — treat as new text expense
        result = extraction_adapter.extract(text, "text")

        if not result.is_complete:
            correction_store.set(
                user_id,
                PendingCorrection(user_id=user_id, original_result=result),
            )

        await _respond_to_extraction(
            update,
            result,
            repository,
            receipt_photo_id=None,
        )

    return handler


async def _respond_to_extraction(
    update: Update,
    result,
    repository: ExpenseRepositoryPort,
    receipt_photo_id: str | None,
) -> None:
    """Respond to an extraction result.

    If complete: save to repo and send formatted summary.
    If partial: ask for missing fields.
    """
    if update.effective_message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    if result.is_complete:
        assert result.amount is not None and result.currency is not None
        assert result.merchant is not None and result.date is not None

        expense = Expense(
            id=None,
            amount=result.amount,
            currency=result.currency,
            merchant=result.merchant,
            date=result.date,
            category=result.category,
            user_id=user_id,
            receipt_photo_id=receipt_photo_id,
            created_at=datetime.now(),
        )
        repository.save(expense)

        summary = (
            f"📄 *Extracted expense:*\n"
            f"Amount: {result.amount} {result.currency}\n"
            f"Merchant: {result.merchant}\n"
            f"Date: {result.date}\n"
            f"Category: {result.category or '—'}\n\n"
            f"✅ Saved."
        )
        await update.effective_message.reply_text(summary)
    else:
        missing = _missing_fields(result)
        await update.effective_message.reply_text(
            f"I extracted partial information. Please reply with the"
            f" missing details: {', '.join(missing)}"
        )


async def _handle_correction(
    update: Update,
    pending: PendingCorrection,
    correction_text: str,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
) -> None:
    """Handle a correction message from a user with a pending partial extraction."""
    if update.effective_message is None or update.effective_user is None:
        return

    user_id = update.effective_user.id

    if pending.maxed_out:
        correction_store.remove(user_id)
        await update.effective_message.reply_text(
            "I couldn't complete the extraction after 3 attempts."
            " Please send a new photo or description."
        )
        return

    refined = extraction_adapter.refine(pending.original_result, correction_text)

    if refined.is_complete:
        assert refined.amount is not None and refined.currency is not None
        assert refined.merchant is not None and refined.date is not None

        # Save and clear pending
        expense = Expense(
            id=None,
            amount=refined.amount,
            currency=refined.currency,
            merchant=refined.merchant,
            date=refined.date,
            category=refined.category,
            user_id=user_id,
            receipt_photo_id=None,
            created_at=datetime.now(),
        )
        repository.save(expense)
        correction_store.remove(user_id)

        summary = (
            f"📄 *Updated expense:*\n"
            f"Amount: {refined.amount} {refined.currency}\n"
            f"Merchant: {refined.merchant}\n"
            f"Date: {refined.date}\n"
            f"Category: {refined.category or '—'}\n\n"
            f"✅ Updated and saved."
        )
        await update.effective_message.reply_text(summary)
    else:
        # Still incomplete — update attempt and ask again
        updated = PendingCorrection(
            user_id=user_id,
            original_result=pending.original_result,
            attempt_count=pending.attempt_count + 1,
        )
        correction_store.set(user_id, updated)

        missing = _missing_fields(refined)
        msg = (
            f"I still could not extract all fields."
            f" Missing: {', '.join(missing)}."
            f" Please provide the missing details."
        )
        await update.effective_message.reply_text(msg)


def _missing_fields(result) -> list[str]:
    """Return a list of field names that are missing from an extraction result."""
    missing: list[str] = []
    if result.amount is None:
        missing.append("amount")
    if result.currency is None:
        missing.append("currency")
    if result.merchant is None:
        missing.append("merchant")
    if result.date is None:
        missing.append("date")
    return missing
