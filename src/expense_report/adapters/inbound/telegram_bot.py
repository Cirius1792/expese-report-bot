"""Telegram bot handlers for expense report bot.

Driving adapter that handles /start, /report, photo, and text messages.
Uses dependency injection for ExpenseRecordingPort and ExpenseRepositoryPort.
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

from expense_report.domain.models import Expense, ExtractionResult
from expense_report.domain.source_types import SourceType
from expense_report.ports.expense_queries import (
    ExpenseQueryPort,
)
from expense_report.ports.expense_recording import (
    CorrectionLimitReached,
    CorrectionOpened,
    CorrectionResolved,
    CorrectionStillIncomplete,
    ExpenseRecorded,
    ExpenseRecordingPort,
    ExtractionIncomplete,
    RecordExpense,
    RecordingMode,
    SourceRejected,
)

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """Welcome! I'm your expense report bot.

Send me a photo of a receipt, a PDF receipt (up to 5 pages), or
describe your expense like "lunch 15 eur".

Commands:
/start - Show this message
/report - Get your monthly expense report as CSV
/list - Browse your expenses by month"""

# Generic user-facing message for unhandled errors (issue #3). Deliberately
# vague: exception details are logged, never sent to the user.
GENERIC_ERROR_MESSAGE = "⚠️ Il servizio non e' al momento disponibile. Riprova piu' tardi."

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


def _make_list_handler(expense_queries: ExpenseQueryPort):
    """Factory: create a /list handler bound to the given query port."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping /list update with no effective message or user")
            return

        user_id = update.effective_user.id

        logger.info("User %s requested /list", user_id)

        # Discover which periods have expenses through the query port
        summary = expense_queries.discover_periods(user_id)

        if not summary.periods:
            await update.effective_message.reply_text(
                "You have no recorded expenses."
                " Send me a photo or describe an expense to get started!"
            )
            return

        # Show the active period's expenses
        expenses = expense_queries.get_month_expenses(
            user_id, summary.active_year, summary.active_month
        )

        text = _format_month_view(expenses, summary.active_year, summary.active_month)
        keyboard = _build_list_keyboard(summary.active_year, summary.periods)

        await update.effective_message.reply_text(text, reply_markup=keyboard)

    return handler


def _make_list_callback_handler(expense_queries: ExpenseQueryPort):
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
        try:
            # Parse callback data first — everything that touches data.split goes here
            if data.startswith("year:"):
                year = int(data.split(":")[1])
                extra_years = {year}
            elif data.startswith("month:"):
                parts = data.split(":")
                if len(parts) != 3:
                    logger.warning("Invalid month callback_data from user %s: %r", user_id, data)
                    return
                year = int(parts[1])
                month = int(parts[2])
                extra_years = {year}
            else:
                return
        except (ValueError, IndexError):
            logger.warning("Invalid callback_data from user %s: %r", user_id, data)
            return

        # Rebuild period info through the query port
        summary = expense_queries.discover_periods(user_id, extra_years=extra_years)

        if data.startswith("year:"):
            logger.info("User %s selected year %s in /list", user_id, year)
            all_expenses = expense_queries.get_year_expenses(user_id, year)
            text = _format_year_view(all_expenses, year)
            keyboard = _build_list_keyboard(year, summary.periods)
            await query.edit_message_text(text=text, reply_markup=keyboard)

        elif data.startswith("month:"):
            logger.info("User %s selected month %s/%s in /list", user_id, year, month)
            expenses = expense_queries.get_month_expenses(user_id, year, month)
            text = _format_month_view(expenses, year, month)
            keyboard = _build_list_keyboard(year, summary.periods)
            await query.edit_message_text(text=text, reply_markup=keyboard)

    return handler


def _make_delete_callback_handler(expense_queries: ExpenseQueryPort):
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

        result = expense_queries.delete_expense(user_id, expense_id)

        if result.deleted is None:
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


def _make_delete_handler(expense_queries: ExpenseQueryPort):
    """Factory: create a /delete command handler bound to the given query port."""

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

        result = expense_queries.delete_expense(user_id, expense_id)

        if result.deleted is None:
            await update.effective_message.reply_text(f"Expense #{expense_id} was not found.")
        else:
            deleted = result.deleted
            await update.effective_message.reply_text(
                f"🗑️ Deleted expense #{deleted.id}:"
                f" {deleted.merchant} — {deleted.amount:.2f} {deleted.currency}"
                f" — {deleted.date}"
            )

    return handler


def register_handlers(
    app: Application,
    expense_recording: ExpenseRecordingPort,
    expense_queries: ExpenseQueryPort,
) -> None:
    """Register all bot command and message handlers."""
    app.add_handler(CommandHandler("start", _handle_start))
    app.add_handler(CommandHandler("report", _make_report_handler(expense_queries)))
    app.add_handler(CommandHandler("list", _make_list_handler(expense_queries)))
    app.add_handler(CommandHandler("delete", _make_delete_handler(expense_queries)))
    app.add_handler(
        CallbackQueryHandler(
            _make_list_callback_handler(expense_queries),
            pattern=r"^(year|month):",
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            _make_delete_callback_handler(expense_queries),
            pattern=r"^delete:",
        )
    )
    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            _make_photo_handler(expense_recording),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.Document.PDF,
            _make_pdf_handler(expense_recording),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            _make_text_handler(expense_recording),
        )
    )


async def handle_unexpected_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global PTB error handler for unhandled exceptions in any bot handler.

    Registered via :func:`register_global_error_handler`. When a handler
    raises, PTB passes (update, context) where ``context.error`` holds the
    exception and ``update`` may be None (e.g. for job callbacks).

    Note: once an error handler is registered, python-telegram-bot no longer
    logs the exception itself (verified against v22.8 ``process_error``), so
    this handler is solely responsible for the ERROR log with traceback.

    The user receives only :data:`GENERIC_ERROR_MESSAGE` — exception details
    never reach the user.
    """
    error = context.error
    logger.error("Unhandled error while processing update: %s", error, exc_info=error)

    if update is None:
        logger.warning("Error handler cannot notify user: no Update available")
        return

    # Stop the pending client spinner on callback updates. The original
    # handler may have answered already — a failed answer must not prevent
    # the user notification below.
    callback_query = getattr(update, "callback_query", None)
    if callback_query is not None:
        try:
            await callback_query.answer()
        except Exception:
            logger.debug("Could not answer callback query in error handler", exc_info=True)

    message = getattr(update, "effective_message", None)
    if message is None:
        logger.warning("Error handler cannot notify user: no effective message in Update")
        return

    try:
        await message.reply_text(GENERIC_ERROR_MESSAGE)
    except Exception:
        logger.error("Failed to deliver generic error message to user", exc_info=True)


def register_global_error_handler(app: Application) -> None:
    """Register the global error handler on the Application.

    Every unhandled exception raised by any handler (commands, photo, text,
    callbacks, authorization guard, future handlers) is then logged with its
    full traceback and acknowledged to the user with a generic message.
    """
    app.add_error_handler(handle_unexpected_error)


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — send welcome message."""
    if update.effective_message is None or update.effective_user is None:
        logger.debug("Skipping /start update with no effective message or user")
        return
    logger.info("User %s started the bot", update.effective_user.id)
    await update.effective_message.reply_text(WELCOME_MESSAGE)


def _make_report_handler(
    expense_queries: ExpenseQueryPort,
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

        csv_string = expense_queries.generate_csv_report(user_id, year, month)

        # Check if report has data (more than just the header line)
        lines = csv_string.strip().split("\n")
        if len(lines) <= 1:
            logger.info("No expenses for user %s in %04d-%02d", user_id, year, month)
            await update.effective_message.reply_text(
                f"No expenses recorded for {year:04d}-{month:02d}."
            )
            return

        filename = f"expenses-{year:04d}-{month:02d}.csv"

        bio = BytesIO(csv_string.encode("utf-8"))
        bio.name = filename

        await update.effective_message.reply_document(document=bio, filename=filename)
        expense_count = len(lines) - 1
        logger.info("Generated report with %s expenses for user %s", expense_count, user_id)
        await update.effective_message.reply_text(
            f"📊 Generated report with {expense_count} expenses."
        )

    return handler


def _make_photo_handler(
    expense_recording: ExpenseRecordingPort,
):
    """Factory: create a photo handler bound to the recording port."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping photo update with no effective message or user")
            return

        user_id = update.effective_user.id
        photo = update.effective_message.photo[-1]

        logger.info("Photo received from user %s", user_id)

        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()

        outcome = expense_recording.record(
            RecordExpense(
                user_id=user_id,
                source=bytes(image_bytes),
                source_type=SourceType.IMAGE,
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=photo.file_id,
            )
        )

        if isinstance(outcome, CorrectionOpened):
            result = outcome.extraction
            missing = _missing_fields(result)
            logger.info(
                "Partial extraction for user %s photo: missing %s",
                user_id,
                ", ".join(missing),
            )
            await _reply_with_incomplete_extraction(update, result)
            return

        logger.info("Complete extraction for user %s photo", user_id)
        if isinstance(outcome, ExpenseRecorded):
            await _reply_with_recorded_expense(update, outcome)

    return handler


def _make_pdf_handler(
    expense_recording: ExpenseRecordingPort,
):
    """Factory: create a PDF document handler bound to the recording port."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping PDF update with no effective message or user")
            return

        user_id = update.effective_user.id
        document = update.effective_message.document
        if document is None:
            logger.debug("Skipping PDF update with no document")
            return

        logger.info("PDF received from user %s", user_id)

        file = await context.bot.get_file(document.file_id)
        pdf_bytes = await file.download_as_bytearray()

        outcome = expense_recording.record(
            RecordExpense(
                user_id=user_id,
                source=bytes(pdf_bytes),
                source_type=SourceType.PDF,
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=None,
            )
        )

        if isinstance(outcome, SourceRejected):
            logger.info("PDF source rejected for user %s: %s", user_id, outcome.reason)
            await update.effective_message.reply_text(outcome.reason)
            return

        if isinstance(outcome, CorrectionOpened):
            result = outcome.extraction
            missing = _missing_fields(result)
            logger.info(
                "Partial extraction for user %s pdf: missing %s",
                user_id,
                ", ".join(missing),
            )
            await _reply_with_incomplete_extraction(update, result)
            return

        logger.info("Complete extraction for user %s pdf", user_id)
        if isinstance(outcome, ExpenseRecorded):
            await _reply_with_recorded_expense(update, outcome)

    return handler


def _make_text_handler(
    expense_recording: ExpenseRecordingPort,
):
    """Factory: create a text handler that delegates all workflow to the recording port."""

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message is None or update.effective_user is None:
            logger.debug("Skipping text update with no effective message or user")
            return

        text = update.effective_message.text
        if text is None:
            logger.debug("Skipping text update with no text content")
            return

        user_id = update.effective_user.id
        logger.info("Text received from user %s", user_id)

        outcome = expense_recording.record(
            RecordExpense(
                user_id=user_id,
                source=text,
                source_type=SourceType.TEXT,
                mode=RecordingMode.CONVERSATIONAL,
                receipt_photo_id=None,
            )
        )

        if isinstance(outcome, ExpenseRecorded):
            await _reply_with_recorded_expense(update, outcome)
        elif isinstance(outcome, CorrectionOpened):
            await _reply_with_incomplete_extraction(update, outcome.extraction)
        elif isinstance(outcome, CorrectionResolved):
            await _reply_with_resolved_correction(update, outcome)
        elif isinstance(outcome, CorrectionStillIncomplete):
            result = outcome.extraction
            missing = _missing_fields(result)
            await update.effective_message.reply_text(
                f"I still could not extract all fields."
                f" Missing: {', '.join(missing)}."
                f" Please provide the missing details."
            )
        elif isinstance(outcome, CorrectionLimitReached):
            await update.effective_message.reply_text(
                "I couldn't complete the extraction after 3 attempts."
                " Please send a new photo or description."
            )
        elif isinstance(outcome, ExtractionIncomplete):
            # ONE_SHOT incomplete — shouldn't arrive for Telegram, but handle gracefully
            await _reply_with_incomplete_extraction(update, outcome.extraction)

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


async def _reply_with_resolved_correction(
    update: Update,
    outcome: "CorrectionResolved",
) -> None:
    """Render the resolved-correction confirmation with delete button."""
    if update.effective_message is None or update.effective_user is None:
        return

    result = outcome.extraction
    saved_expense = outcome.expense
    logger.info("Saved expense %s for user %s", saved_expense.id, update.effective_user.id)
    summary = (
        f"📄 *Updated expense:*\n"
        f"Expense #{saved_expense.id}\n"
        f"Amount: {result.amount} {result.currency}\n"
        f"Merchant: {result.merchant}\n"
        f"Date: {result.date}\n"
        f"Category: {result.category or '—'}\n\n"
        f"✅ Updated and saved."
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete:{saved_expense.id}")]]
    )
    await update.effective_message.reply_text(summary, reply_markup=keyboard)


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


def _missing_fields(result: ExtractionResult) -> list[str]:
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
