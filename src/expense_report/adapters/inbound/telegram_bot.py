"""Telegram bot handlers for expense report bot.

Driving adapter that handles /start, /report, photo, and text messages.
Uses dependency injection for ExtractionPort and ExpenseRepositoryPort.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from html import escape as _html_escape
from io import BytesIO

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from expense_report.domain.correction_state import CorrectionStore, PendingCorrection
from expense_report.domain.csv_generator import generate_csv
from expense_report.domain.models import Expense, ExtractionResult
from expense_report.ports.expense_recording import (
    ExpenseRecorded,
    ExpenseRecordingPort,
    ExtractionIncomplete,
    RecordExpense,
    RecordingMode,
)
from expense_report.ports.extraction import ExtractionPort
from expense_report.ports.repository import ExpenseRepositoryPort

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """Welcome! I'm your expense report bot.

Send me a photo of a receipt, or describe your expense like "lunch 15 eur".

Commands:
/start - Show this message
/report - Get your monthly expense report as CSV
/list - Browse your expenses by month"""

_MONTH_NAMES: dict[int, str] = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

_FULL_MONTH_NAMES: dict[int, str] = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def _format_month_view(expenses: list[Expense], year: int, month: int) -> str:
    """Format a list of expenses as a month-view message text."""
    month_name = _FULL_MONTH_NAMES.get(month, str(month))

    if not expenses:
        return f"📊 {month_name} {year}\n\nNo expenses recorded for this month."

    lines = [f"📊 {month_name} {year}\n"]

    totals_by_currency: dict[str, Decimal] = {}
    for e in expenses:
        lines.append(
            f"#{e.id:<4} {e.date}  {e.merchant:<20}"
            f" {e.amount:>8.2f} {e.currency:<4} {e.category or ''}"
        )
        totals_by_currency[e.currency] = (
            totals_by_currency.get(e.currency, Decimal("0.00")) + e.amount
        )

    total_parts = [f"{total:.2f} {curr}" for curr, total in totals_by_currency.items()]
    lines.append(f"\nTotal: {', '.join(total_parts)} ({len(expenses)} expenses)")
    lines.append("\nOnly months with recorded expenses are shown below.")

    return "\n".join(lines)


def _format_year_view(expenses: list[Expense], year: int) -> str:
    """Format a year aggregate as a message text, grouped by currency."""
    if not expenses:
        return (
            f"📊 {year} Summary\n\n"
            f"No expenses recorded for this year.\n\n"
            f"Tap a month below for details."
        )

    totals_by_currency: dict[str, Decimal] = {}
    for e in expenses:
        totals_by_currency[e.currency] = (
            totals_by_currency.get(e.currency, Decimal("0.00")) + e.amount
        )

    total_parts = [f"{total:.2f} {curr}" for curr, total in totals_by_currency.items()]
    return f"📊 {year} Summary\n\nTotal: {', '.join(total_parts)}\n\nTap a month below for details."


def _build_list_keyboard(
    active_year: int,
    year_months: dict[int, set[int]],
) -> InlineKeyboardMarkup:
    """Build an inline keyboard with year and month buttons.

    Args:
        active_year: The currently selected year.
        year_months: Mapping of year -> set of month numbers with expenses.

    Returns:
        An InlineKeyboardMarkup with year row and month row.
    """
    keyboard: list[list[InlineKeyboardButton]] = []

    # Year row — descending order
    years = sorted(year_months.keys(), reverse=True)
    if years:
        year_buttons = [InlineKeyboardButton(str(y), callback_data=f"year:{y}") for y in years]
        keyboard.append(year_buttons)

    # Month row — chronological order, only months with expenses for active year
    months = sorted(year_months.get(active_year, set()))
    if months:
        month_buttons = [
            InlineKeyboardButton(
                _MONTH_NAMES[m],
                callback_data=f"month:{active_year}:{m}",
            )
            for m in months
        ]
        keyboard.append(month_buttons)

    return InlineKeyboardMarkup(keyboard)


def _make_list_handler(repository: ExpenseRepositoryPort):
    """Factory: create a /list handler bound to the given repository."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping /list update with no effective message or user")
            return

        user_id = update.effective_user.id
        now = datetime.now()
        current_year = now.year
        current_month = now.month

        logger.info("User %s requested /list", user_id)

        # Discover which years and months have expenses
        year_months: dict[int, set[int]] = {}

        current_year_months = repository.get_months_with_expenses(user_id, current_year)
        if current_year_months:
            year_months[current_year] = current_year_months

        prev_year_months = repository.get_months_with_expenses(user_id, current_year - 1)
        if prev_year_months:
            year_months[current_year - 1] = prev_year_months

        if not year_months:
            await update.effective_message.reply_text(
                "You have no recorded expenses."
                " Send me a photo or describe an expense to get started!"
            )
            return

        # If current year has no data but previous years do, use the most recent year
        if current_year not in year_months:
            active_year = max(year_months.keys())
            active_month = max(year_months[active_year])
        else:
            active_year = current_year
            active_month = current_month

        # Show the active month's expenses
        expenses = repository.get_by_user_and_month(user_id, active_year, active_month)

        text = _format_month_view(expenses, active_year, active_month)
        keyboard = _build_list_keyboard(active_year, year_months)

        await update.effective_message.reply_text(text, reply_markup=keyboard)

    return handler


def _make_list_callback_handler(repository: ExpenseRepositoryPort):
    """Factory: create a callback handler for /list inline keyboard buttons."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            logger.debug("Skipping callback with no CallbackQuery")
            return

        await query.answer()
        data = query.data
        if data is None:
            return

        user_id = query.from_user.id
        now = datetime.now()

        try:
            # Parse callback data first — everything that touches data.split goes here
            if data.startswith("year:"):
                year = int(data.split(":")[1])
                years_to_check = {now.year, now.year - 1, year}
            elif data.startswith("month:"):
                parts = data.split(":")
                if len(parts) != 3:
                    logger.warning("Invalid month callback_data from user %s: %r", user_id, data)
                    return
                year = int(parts[1])
                month = int(parts[2])
                years_to_check = {now.year, now.year - 1, year}
            else:
                return
        except (ValueError, IndexError):
            logger.warning("Invalid callback_data from user %s: %r", user_id, data)
            return

        # Rebuild year_months for keyboard
        year_months: dict[int, set[int]] = {}
        for y in years_to_check:
            months = repository.get_months_with_expenses(user_id, y)
            if months:
                year_months[y] = months

        if data.startswith("year:"):
            logger.info("User %s selected year %s in /list", user_id, year)
            all_expenses: list[Expense] = []
            for m in year_months.get(year, set()):
                all_expenses.extend(repository.get_by_user_and_month(user_id, year, m))
            text = _format_year_view(all_expenses, year)
            keyboard = _build_list_keyboard(year, year_months)
            await query.edit_message_text(text=text, reply_markup=keyboard)

        elif data.startswith("month:"):
            logger.info("User %s selected month %s/%s in /list", user_id, year, month)
            expenses = repository.get_by_user_and_month(user_id, year, month)
            text = _format_month_view(expenses, year, month)
            keyboard = _build_list_keyboard(year, year_months)
            await query.edit_message_text(text=text, reply_markup=keyboard)

    return handler


def _make_delete_callback_handler(repository: ExpenseRepositoryPort):
    """Factory: create a callback handler for delete button presses.

    Handles callback data of the form 'delete:<expense_id>'.
    """

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None:
            logger.debug("Skipping delete callback with no CallbackQuery")
            return

        await query.answer()
        data = query.data
        if data is None or not data.startswith("delete:"):
            return

        user_id = query.from_user.id
        try:
            expense_id = int(data.split(":", 1)[1])
        except (ValueError, IndexError):
            logger.warning("Invalid delete callback_data from user %s: %r", user_id, data)
            return

        logger.info("User %s tapped delete for expense #%s", user_id, expense_id)

        deleted = repository.delete_by_id(user_id, expense_id)

        if deleted is None:
            await query.answer("Expense not found.")
            return

        # Get original message text and wrap in strikethrough
        original_text = ""
        if query.message is not None:
            original_text = (
                getattr(query.message, "text", None)
                or getattr(query.message, "caption", None)
                or ""
            )

        escaped_text = _html_escape(original_text)
        new_text = f"<s>{escaped_text}</s>\n\n🗑️ Deleted."

        await query.edit_message_text(
            text=new_text,
            parse_mode="HTML",
        )

    return handler


def _make_delete_handler(repository: ExpenseRepositoryPort):
    """Factory: create a /delete command handler bound to the given repository."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping /delete update with no effective message or user")
            return

        user_id = update.effective_user.id
        text = update.effective_message.text or ""

        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await update.effective_message.reply_text("Usage: /delete <expense_id>")
            return

        id_str = parts[1].strip()

        try:
            expense_id = int(id_str)
        except ValueError:
            await update.effective_message.reply_text("Usage: /delete <expense_id>")
            return

        if expense_id <= 0:
            await update.effective_message.reply_text("Usage: /delete <expense_id>")
            return

        logger.info("User %s requesting deletion of expense #%s", user_id, expense_id)

        deleted = repository.delete_by_id(user_id, expense_id)

        if deleted is None:
            await update.effective_message.reply_text(f"Expense #{expense_id} was not found.")
        else:
            await update.effective_message.reply_text(
                f"🗑️ Deleted expense #{deleted.id}:"
                f" {deleted.merchant} — {deleted.amount:.2f} {deleted.currency}"
                f" — {deleted.date}"
            )

    return handler


def register_handlers(
    app: Application,
    expense_recording: ExpenseRecordingPort,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
) -> None:
    """Register all bot command and message handlers."""
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("report", _make_report_handler(repository)))
    app.add_handler(CommandHandler("list", _make_list_handler(repository)))
    app.add_handler(CommandHandler("delete", _make_delete_handler(repository)))
    app.add_handler(
        CallbackQueryHandler(
            _make_list_callback_handler(repository),
            pattern=r"^(year|month):",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            _make_delete_callback_handler(repository),
            pattern=r"^delete:",
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            _make_photo_handler(extraction_adapter, repository, correction_store),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _make_text_handler(expense_recording, extraction_adapter, repository, correction_store),
        )
    )


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — send welcome message."""
    if update.effective_message is None or update.effective_user is None:
        logger.debug("Skipping /start update with no effective message or user")
        return
    logger.info("User %s started the bot", update.effective_user.id)
    await update.effective_message.reply_text(WELCOME_MESSAGE)


def _make_report_handler(
    repository: ExpenseRepositoryPort,
):
    """Factory: create a /report handler bound to the given repository."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping /report update with no effective message or user")
            return

        user_id = update.effective_user.id
        now = datetime.now()
        year = now.year
        month = now.month

        logger.info("User %s requested report for %04d-%02d", user_id, year, month)

        expenses = repository.get_by_user_and_month(user_id, year, month)

        if not expenses:
            logger.info("No expenses for user %s in %04d-%02d", user_id, year, month)
            await update.effective_message.reply_text(
                f"No expenses recorded for {year:04d}-{month:02d}."
            )
            return

        csv_string = generate_csv(expenses)
        filename = f"expenses-{year:04d}-{month:02d}.csv"

        bio = BytesIO(csv_string.encode("utf-8"))
        bio.name = filename

        await update.effective_message.reply_document(document=bio, filename=filename)
        logger.info("Generated report with %s expenses for user %s", len(expenses), user_id)
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
            logger.debug("Skipping photo update with no effective message or user")
            return

        user_id = update.effective_user.id
        photo = update.effective_message.photo[-1]

        logger.info("Photo received from user %s", user_id)

        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        result = extraction_adapter.extract(bytes(image_bytes), "image")

        if not result.is_complete:
            missing = _missing_fields(result)
            logger.info(
                "Partial extraction for user %s photo: missing %s",
                user_id,
                ", ".join(missing),
            )
            correction_store.set(
                user_id,
                PendingCorrection(
                    user_id=user_id,
                    original_result=result,
                ),
            )
        else:
            logger.info("Complete extraction for user %s photo", user_id)

        await _respond_to_extraction(
            update,
            result,
            repository,
            receipt_photo_id=photo.file_id,
        )

    return handler


def _make_text_handler(
    expense_recording: ExpenseRecordingPort,
    extraction_adapter: ExtractionPort,
    repository: ExpenseRepositoryPort,
    correction_store: CorrectionStore,
):
    """Factory: create a text handler bound to the given adapters."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping text update with no effective message or user")
            return

        text = update.effective_message.text
        if text is None:
            logger.debug("Skipping text update with no text content")
            return

        user_id = update.effective_user.id
        pending = correction_store.get(user_id)

        if pending is not None:
            logger.info(
                "Correction received from user %s (attempt %s/3)",
                user_id,
                pending.attempt_count,
            )
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
        logger.info("Text received from user %s", user_id)
        outcome = expense_recording.record(
            RecordExpense(
                user_id=user_id,
                source=text,
                source_type="text",
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=None,
            )
        )

        if isinstance(outcome, ExtractionIncomplete):
            result = outcome.extraction
            missing = _missing_fields(result)
            logger.info(
                "Partial extraction for user %s text: missing %s",
                user_id,
                ", ".join(missing),
            )
            correction_store.set(
                user_id,
                PendingCorrection(user_id=user_id, original_result=result),
            )
            await _reply_with_incomplete_extraction(update, result)
            return

        logger.info("Complete extraction for user %s text", user_id)
        await _reply_with_recorded_expense(update, outcome)

    return handler


async def _reply_with_recorded_expense(
    update: Update,
    outcome: ExpenseRecorded,
) -> None:
    if update.effective_message is None or update.effective_user is None:
        return

    result = outcome.extraction
    saved_expense = outcome.expense
    logger.info("Saved expense %s for user %s", saved_expense.id, update.effective_user.id)
    summary = (
        f"📄 *Extracted expense:*\n"
        f"Expense #{saved_expense.id}\n"
        f"Amount: {result.amount} {result.currency}\n"
        f"Merchant: {result.merchant}\n"
        f"Date: {result.date}\n"
        f"Category: {result.category or '—'}\n\n"
        f"✅ Saved."
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{saved_expense.id}")]]
    )
    await update.effective_message.reply_text(summary, reply_markup=keyboard)


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
        saved_expense = repository.save(expense)
        logger.info(
            "Saved expense %s for user %s",
            saved_expense.id,
            user_id,
        )

        await _reply_with_recorded_expense(
            update,
            ExpenseRecorded(expense=saved_expense, extraction=result),
        )
    else:
        await _reply_with_incomplete_extraction(update, result)


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
        logger.info(
            "Correction maxed out for user %s (attempt %s/3), clearing",
            user_id,
            pending.attempt_count,
        )
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
        saved_expense = repository.save(expense)
        correction_store.remove(user_id)
        logger.info(
            "Correction resolved for user %s: saved updated expense",
            user_id,
        )

        summary = (
            f"📄 *Updated expense:*\n"
            f"Expense #{saved_expense.id}\n"
            f"Amount: {refined.amount} {refined.currency}\n"
            f"Merchant: {refined.merchant}\n"
            f"Date: {refined.date}\n"
            f"Category: {refined.category or '—'}\n\n"
            f"✅ Updated and saved."
        )
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{saved_expense.id}")]]
        )
        await update.effective_message.reply_text(summary, reply_markup=keyboard)
    else:
        # Still incomplete — update attempt and ask again
        updated = PendingCorrection(
            user_id=user_id,
            original_result=pending.original_result,
            attempt_count=pending.attempt_count + 1,
        )
        correction_store.set(user_id, updated)
        logger.info(
            "Correction still incomplete for user %s (attempt %s)",
            user_id,
            updated.attempt_count,
        )

        missing = _missing_fields(refined)
        msg = (
            f"I still could not extract all fields."
            f" Missing: {', '.join(missing)}."
            f" Please provide the missing details."
        )
        await update.effective_message.reply_text(msg)


async def _reply_with_incomplete_extraction(
    update: Update,
    result: ExtractionResult,
) -> None:
    if update.effective_message is None:
        return
    missing = _missing_fields(result)
    await update.effective_message.reply_text(
        f"I extracted partial information. Please reply with the"
        f" missing details: {', '.join(missing)}"
    )


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
