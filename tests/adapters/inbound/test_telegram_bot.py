"""Tests for Telegram bot handlers.

Uses mocked telegram module (set up in tests/conftest.py) and
AsyncMock for async PTB API methods.

Follows sociable unit test principles:
- System boundaries mocked: Telegram API (PTB), LLM (extraction adapter mock), DB (repository mock)
- Internal collaborators are real: CorrectionStore (domain class)
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from expense_report.domain.correction_state import CorrectionStore, PendingCorrection
from expense_report.domain.models import Expense, ExtractionResult


def _make_update(
    user_id: int = 12345,
    text: str | None = None,
    photo_file_id: str | None = None,
) -> MagicMock:
    """Create a mock Telegram Update with the given attributes."""
    update = MagicMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.reply_document = AsyncMock()
    update.effective_message.text = text
    update.effective_user = MagicMock()
    update.effective_user.id = user_id

    if photo_file_id is not None:
        mock_photo = MagicMock()
        mock_photo.file_id = photo_file_id
        update.effective_message.photo = [MagicMock(), mock_photo]

    return update


def _make_context(
    image_bytes: bytes = b"fake-image-data",
) -> MagicMock:
    """Create a mock CallbackContext with get_file returning mock file."""
    context = MagicMock()
    mock_file = MagicMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=image_bytes)
    context.bot.get_file = AsyncMock(return_value=mock_file)
    return context


class TestStartHandler:
    """Tests for /start command handler."""

    def test_sends_welcome_message(self) -> None:
        """Handler replies with the welcome message."""
        from expense_report.adapters.inbound.telegram_bot import (
            WELCOME_MESSAGE,
            _handle_start,
        )

        update = _make_update()
        context = MagicMock()

        asyncio.run(_handle_start(update, context))

        update.effective_message.reply_text.assert_awaited_once_with(WELCOME_MESSAGE)

    def test_no_message_does_nothing(self) -> None:
        """When effective_message is None, handler returns silently."""
        from expense_report.adapters.inbound.telegram_bot import _handle_start

        update = MagicMock()
        update.effective_message = None
        context = MagicMock()

        asyncio.run(_handle_start(update, context))
        # No error — handler returns early


class TestPhotoHandler:
    """Tests for photo message handler."""

    def test_complete_extraction_saves_and_confirms(self) -> None:
        """Photo with complete extraction saves expense and replies with summary."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Supermarket",
            date=date(2026, 7, 15),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()  # real domain object

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(photo_file_id="photo-abc-123")
        context = _make_context(image_bytes=b"receipt-image")

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        adapter.extract.assert_called_once_with(b"receipt-image", "image")
        repo.save.assert_called_once()

        saved_expense: Expense = repo.save.call_args[0][0]
        assert isinstance(saved_expense, Expense)
        assert saved_expense.amount == Decimal("42.50")
        assert saved_expense.merchant == "Supermarket"
        assert saved_expense.receipt_photo_id == "photo-abc-123"
        assert saved_expense.user_id == 12345

        # Verify no correction was stored (complete extraction)
        assert store.get(12345) is None

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "✅ Saved." in reply_text
        assert "42.50" in reply_text
        assert "EUR" in reply_text
        assert "Supermarket" in reply_text

    def test_partial_extraction_asks_for_missing(self) -> None:
        """Photo with partial extraction asks user for missing fields."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        repo = MagicMock()
        store = CorrectionStore()  # real domain object

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(photo_file_id="photo-456")
        context = _make_context(image_bytes=b"blurry-receipt")

        asyncio.run(handler(update, context))

        adapter.extract.assert_called_once_with(b"blurry-receipt", "image")
        repo.save.assert_not_called()

        # Verify correction was stored (real store, not mock assertion)
        pending = store.get(12345)
        assert pending is not None
        assert pending.user_id == 12345
        assert pending.original_result.amount == Decimal("15.00")
        assert pending.attempt_count == 1

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "partial information" in reply_text
        assert "currency" in reply_text
        assert "merchant" in reply_text
        assert "date" in reply_text
        assert "amount" not in reply_text  # amount was provided


class TestTextHandler:
    """Tests for text message handler."""

    def test_complete_extraction_saves_and_confirms(self) -> None:
        """Text with complete extraction saves expense and replies."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()  # real domain object, no pending correction

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="coffee 12.50 usd")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        adapter.extract.assert_called_once_with("coffee 12.50 usd", "text")
        repo.save.assert_called_once()

        saved_expense: Expense = repo.save.call_args[0][0]
        assert saved_expense.amount == Decimal("12.50")
        assert saved_expense.merchant == "Coffee Shop"
        assert saved_expense.receipt_photo_id is None

        # Verify no correction was stored for this user
        assert store.get(12345) is None

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "✅ Saved." in reply_text
        assert "12.50 USD" in reply_text

    def test_partial_extraction_asks_for_missing(self) -> None:
        """Text with partial extraction asks user for missing fields."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        repo = MagicMock()
        store = CorrectionStore()  # real domain object, no pending correction

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="something")
        context = MagicMock()

        asyncio.run(handler(update, context))

        repo.save.assert_not_called()

        # Verify correction was stored
        pending = store.get(12345)
        assert pending is not None
        assert pending.attempt_count == 1

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "partial information" in reply_text
        assert "amount" in reply_text
        assert "currency" in reply_text
        assert "merchant" in reply_text
        assert "date" in reply_text


class TestReportHandler:
    """Tests for /report command handler."""

    def test_with_expenses_sends_csv(self) -> None:
        """Report with expenses sends CSV document and count message."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="Shop A",
                date=date(2026, 7, 1),
                category="shopping",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            ),
            Expense(
                id="e2",
                amount=Decimal("20.50"),
                currency="EUR",
                merchant="Shop B",
                date=date(2026, 7, 2),
                category="food",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 2, 11, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 7)

        # Verify document was sent
        update.effective_message.reply_document.assert_awaited_once()
        doc_call = update.effective_message.reply_document.call_args[1]
        assert doc_call["filename"] == "expenses-2026-07.csv"
        # Verify content is valid CSV
        bio = doc_call["document"]
        csv_content = bio.getvalue().decode("utf-8")
        assert "date,merchant,category,amount,currency" in csv_content
        assert "Shop A" in csv_content
        assert "Shop B" in csv_content

        # Verify count message
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "Generated report with 2 expenses" in reply_text

    def test_no_expenses_reports_empty(self) -> None:
        """Report with no expenses sends 'no expenses' message."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 7)
        update.effective_message.reply_document.assert_not_awaited()

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "No expenses recorded for 2026-07" in reply_text

    def test_multi_user_isolation(self) -> None:
        """Each user only sees their own expenses (user_id passed to repo)."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update(user_id=99999)
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_by_user_and_month.assert_called_once_with(99999, 2026, 7)


class TestRegisterHandlers:
    """Tests that register_handlers wires up the Application correctly."""

    def test_registers_all_handlers(self) -> None:
        """register_handlers adds 6 handlers to the Application.

        In the mocked environment, all handler objects are MagicMock
        instances. We verify the count and that the registration
        doesn't raise.
        """
        from expense_report.adapters.inbound.telegram_bot import (
            register_handlers,
        )

        app = MagicMock()
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        register_handlers(app, adapter, repo, store)

        # Verify 7 handlers were registered
        assert app.add_handler.call_count == 7
        # Expected: CommandHandler(start), CommandHandler(report), CommandHandler(list),
        #           CallbackQueryHandler, MessageHandler(photo), MessageHandler(text)


class TestMissingFields:
    """Tests for _missing_fields helper."""

    def test_returns_all_missing(self) -> None:
        """When all fields None, returns all four field names."""
        from expense_report.adapters.inbound.telegram_bot import _missing_fields

        result = ExtractionResult(
            amount=None,
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        missing = _missing_fields(result)
        assert missing == ["amount", "currency", "merchant", "date"]

    def test_returns_none_when_all_present(self) -> None:
        """When all mandatory fields present, returns empty list."""
        from expense_report.adapters.inbound.telegram_bot import _missing_fields

        result = ExtractionResult(
            amount=Decimal("10.00"),
            currency="EUR",
            merchant="Shop",
            date=date(2026, 7, 1),
            category="food",
        )
        missing = _missing_fields(result)
        assert missing == []

    def test_only_missing_fields_returned(self) -> None:
        """Only fields that are None are included in the missing list."""
        from expense_report.adapters.inbound.telegram_bot import _missing_fields

        result = ExtractionResult(
            amount=Decimal("10.00"),
            currency=None,
            merchant="Shop",
            date=None,
            category=None,
        )
        missing = _missing_fields(result)
        assert missing == ["currency", "date"]


class TestCorrectionFlow:
    """Tests for correction flow (partial extraction → user corrects → refine).

    Uses real CorrectionStore — tests verify state transitions through the
    domain object, not mock assertions on the store.
    """

    def test_text_handler_with_pending_correction_refine_complete_saves_and_removes(
        self,
    ) -> None:
        """Text pending correction: refine completes → save, remove from store."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        # Setup: pre-populate with a pending correction
        original = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        store.set(
            12345, PendingCorrection(user_id=12345, original_result=original, attempt_count=1)
        )

        refined = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Cafe",
            date=date(2026, 7, 20),
            category=None,
        )
        adapter.refine.return_value = refined

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="Cafe EUR 15")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        # Verify refine was called with original + correction text
        adapter.refine.assert_called_once_with(original, "Cafe EUR 15")
        # Verify complete result was saved
        repo.save.assert_called_once()
        saved: Expense = repo.save.call_args[0][0]
        assert saved.amount == Decimal("15.00")
        assert saved.merchant == "Cafe"
        # Verify store was cleared (real store check)
        assert store.get(12345) is None
        # Verify confirmation message
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "Updated and saved" in reply_text

    def test_text_handler_with_pending_correction_still_incomplete_asks_again(
        self,
    ) -> None:
        """Text pending correction: refine still incomplete → ask again, increment attempt."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        original = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        store.set(
            12345, PendingCorrection(user_id=12345, original_result=original, attempt_count=1)
        )

        # Refine result still missing currency, date
        refined = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant="Cafe",
            date=None,
            category=None,
        )
        adapter.refine.return_value = refined

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="Cafe")
        context = MagicMock()

        asyncio.run(handler(update, context))

        # Verify refine was called
        adapter.refine.assert_called_once_with(original, "Cafe")
        # Verify not saved
        repo.save.assert_not_called()
        # Verify store was updated with incremented attempt (real store check)
        pending = store.get(12345)
        assert pending is not None
        assert pending.attempt_count == 2
        assert pending.original_result.amount == Decimal("15.00")
        # Verify reply asks for missing fields again
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "partial" in reply_text or "missing" in reply_text
        assert "currency" in reply_text
        assert "date" in reply_text

    def test_text_handler_with_pending_correction_maxed_out_removes_and_fails(
        self,
    ) -> None:
        """Text pending correction: maxed out (3rd attempt) → remove, send failure."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        original = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        store.set(
            12345, PendingCorrection(user_id=12345, original_result=original, attempt_count=3)
        )

        # Even a perfect refine result — but 3 attempts already exhausted
        refined = ExtractionResult(
            amount=Decimal("15.00"),
            currency="EUR",
            merchant="Cafe",
            date=date(2026, 7, 20),
            category=None,
        )
        adapter.refine.return_value = refined

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="Cafe EUR 2026-07-20")
        context = MagicMock()

        asyncio.run(handler(update, context))

        # Verify refine was NOT called (we maxed out before the attempt)
        adapter.refine.assert_not_called()
        # Verify not saved
        repo.save.assert_not_called()
        # Verify store was removed (real store check)
        assert store.get(12345) is None
        # Verify failure message
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "3 attempts" in reply_text or "could not complete" in reply_text

    def test_photo_handler_partial_extraction_creates_pending_correction(
        self,
    ) -> None:
        """Photo partial extraction stores pending correction before asking."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        partial = ExtractionResult(
            amount=Decimal("25.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        adapter.extract.return_value = partial

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(photo_file_id="photo-789")
        context = _make_context(image_bytes=b"receipt-img")

        asyncio.run(handler(update, context))

        # Verify correction was stored (real store check)
        pending = store.get(12345)
        assert pending is not None
        assert pending.original_result.amount == Decimal("25.00")
        assert pending.user_id == 12345
        assert pending.attempt_count == 1
        # Verify repo was NOT saved
        repo.save.assert_not_called()
        # Verify missing fields message was sent
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "partial information" in reply_text

    def test_photo_handler_complete_extraction_no_pending_correction(
        self,
    ) -> None:
        """Photo complete extraction does NOT create pending correction."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()  # real store

        complete = ExtractionResult(
            amount=Decimal("30.00"),
            currency="USD",
            merchant="Gas Station",
            date=date(2026, 7, 22),
            category="transport",
        )
        adapter.extract.return_value = complete

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(photo_file_id="photo-101112")
        context = _make_context(image_bytes=b"receipt-good")

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 22, 9, 0, 0)
            asyncio.run(handler(update, context))

        # Verify no correction was stored (real store check)
        assert store.get(12345) is None
        # Verify repo was saved
        repo.save.assert_called_once()
        saved: Expense = repo.save.call_args[0][0]
        assert saved.amount == Decimal("30.00")
        assert saved.merchant == "Gas Station"

    def test_text_handler_without_pending_correction_normal_flow(
        self,
    ) -> None:
        """Text handler without pending correction: normal new expense extraction."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()  # real store, empty (no pending correction)

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(text="coffee 12.50 usd")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        # Verify normal extraction flow
        adapter.extract.assert_called_once_with("coffee 12.50 usd", "text")
        repo.save.assert_called_once()
        # Verify store was never touched (real store check)
        assert store.get(12345) is None
        # Verify confirmation
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "✅ Saved." in reply_text


class TestListHandler:
    """Tests for /list command handler with inline keyboard."""

    def test_shows_current_month_expenses_and_total(self) -> None:
        """List handler shows current month expenses and total."""
        repo = MagicMock()
        repo.get_months_with_expenses.return_value = {7, 3}
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("42.50"),
                currency="EUR",
                merchant="Supermarket",
                date=date(2026, 7, 10),
                category="food",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 10, 10, 0, 0),
            ),
            Expense(
                id="e2",
                amount=Decimal("12.50"),
                currency="EUR",
                merchant="Coffee Shop",
                date=date(2026, 7, 20),
                category="food",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 20, 11, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_months_with_expenses.assert_any_call(12345, 2026)
        repo.get_months_with_expenses.assert_any_call(12345, 2025)
        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 7)

        # Verify reply includes expense data and total
        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "Supermarket" in reply_text
        assert "Coffee Shop" in reply_text
        assert "55.00" in reply_text
        assert "July 2026" in reply_text

        # Verify reply_markup is an InlineKeyboardMarkup (ANY as placeholder since we mock)
        assert "reply_markup" in update.effective_message.reply_text.call_args[1]

    def test_shows_current_month_and_year_buttons(self) -> None:
        """List handler generates correct inline button labels."""

        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7, 3},  # 2026
            set(),  # 2025 (none)
        ]
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("42.50"),
                currency="EUR",
                merchant="Shop",
                date=date(2026, 7, 10),
                category=None,
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 10, 10, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
        keyboard = markup.inline_keyboard

        # Year row: only 2026 (2025 has no expenses)
        year_buttons = [btn.text for btn in keyboard[0]]
        assert year_buttons == ["2026"]
        assert keyboard[0][0].callback_data == "year:2026"

        # Month row: Jul and Mar
        month_buttons = [btn.text for btn in keyboard[1]]
        assert month_buttons == ["Mar", "Jul"]
        assert keyboard[1][0].callback_data == "month:2026:3"
        assert keyboard[1][1].callback_data == "month:2026:7"

    def test_previous_year_button_when_expenses_exist(self) -> None:
        """Both 2026 and 2025 buttons shown when both years have expenses."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7},  # 2026
            {12, 1},  # 2025
        ]
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="Shop",
                date=date(2026, 7, 1),
                category=None,
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
        keyboard = markup.inline_keyboard

        year_buttons = [btn.text for btn in keyboard[0]]
        assert year_buttons == ["2026", "2025"]

    def test_no_expenses_shows_informative_message(self) -> None:
        """When no expenses exist at all, show message without buttons."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            set(),  # 2026
            set(),  # 2025
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        reply_text = update.effective_message.reply_text.call_args[0][0]
        assert "no" in reply_text.lower()
        assert "reply_markup" not in update.effective_message.reply_text.call_args[1]

    def test_previous_year_only_shows_that_year(self) -> None:
        """When user has expenses only in previous year, shows that year's data."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            set(),  # 2026 — no data
            {12},  # 2025 — only December
        ]
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("15.00"),
                currency="EUR",
                merchant="Old Shop",
                date=date(2025, 12, 1),
                category="shopping",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2025, 12, 1, 10, 0, 0),
            ),
        ]

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update()
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        # Should query 2025-12, not current 2026-07
        repo.get_by_user_and_month.assert_called_once_with(12345, 2025, 12)

        markup = update.effective_message.reply_text.call_args[1]["reply_markup"]
        keyboard = markup.inline_keyboard
        year_buttons = [btn.text for btn in keyboard[0]]
        assert year_buttons == ["2025"]
        month_buttons = [btn.text for btn in keyboard[1]]
        assert month_buttons == ["Dec"]

    def test_multi_user_isolation(self) -> None:
        """User 99999 sees a different user_id passed to repo."""
        repo = MagicMock()
        repo.get_months_with_expenses.side_effect = [
            {7},
            set(),
        ]
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import _make_list_handler

        handler = _make_list_handler(repo)
        update = _make_update(user_id=99999)
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        repo.get_months_with_expenses.assert_any_call(99999, 2026)
        repo.get_by_user_and_month.assert_called_once_with(99999, 2026, 7)

    def test_format_month_view_includes_expense_ids(self) -> None:
        """Month view shows integer expense IDs for /delete reference."""
        from expense_report.adapters.inbound.telegram_bot import _format_month_view

        expenses = [
            Expense(
                id=42,
                amount=Decimal("42.50"),
                currency="EUR",
                merchant="Supermarket",
                date=date(2026, 7, 10),
                category="groceries",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 10, 12, 0, 0),
            ),
        ]

        text = _format_month_view(expenses, 2026, 7)

        assert "#42" in text


def _make_callback_update(
    user_id: int = 12345,
    callback_data: str = "",
) -> MagicMock:
    """Create a mock Telegram Update with a CallbackQuery."""
    update = MagicMock()
    query = MagicMock()
    query.data = callback_data
    query.from_user = MagicMock()
    query.from_user.id = user_id
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query
    update.effective_message = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


class TestListCallbackHandler:
    """Tests for /list inline keyboard callback handler."""

    def test_month_callback_updates_message(self) -> None:
        """Tapping a month button edits the message to show that month."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("30.00"),
                currency="EUR",
                merchant="Book Store",
                date=date(2026, 3, 5),
                category="shopping",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 3, 5, 10, 0, 0),
            ),
        ]
        repo.get_months_with_expenses.side_effect = lambda uid, year: {
            2026: {7, 3},
            2025: set(),
        }.get(year, set())

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="month:2026:3")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        # Verify query.answer() was called
        update.callback_query.answer.assert_awaited_once()

        # Verify repository was called for the correct month
        repo.get_by_user_and_month.assert_called_once_with(12345, 2026, 3)

        # Verify edit_message_text was called with expense data
        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "Book Store" in edit_call["text"]
        assert "30.00" in edit_call["text"]

        # Verify keyboard was included
        markup = edit_call["reply_markup"]
        keyboard = markup.inline_keyboard
        month_buttons = [btn.text for btn in keyboard[1]]
        assert "Mar" in month_buttons
        assert "Jul" in month_buttons

    def test_year_callback_shows_year_total(self) -> None:
        """Tapping a year button shows year aggregate grouped by currency."""
        repo = MagicMock()
        # get_by_user_and_month returns expenses for each month
        repo.get_by_user_and_month.return_value = [
            Expense(
                id="e1",
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="Old Shop",
                date=date(2025, 12, 1),
                category="shopping",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2025, 12, 1, 10, 0, 0),
            ),
            Expense(
                id="e2",
                amount=Decimal("5.00"),
                currency="EUR",
                merchant="Another",
                date=date(2025, 12, 10),
                category=None,
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2025, 12, 10, 10, 0, 0),
            ),
        ]
        repo.get_months_with_expenses.return_value = {12}

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="year:2025")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        update.callback_query.answer.assert_awaited_once()

        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "2025 Summary" in edit_call["text"]
        assert "15.00 EUR" in edit_call["text"]

        # Month row shows Dec
        markup = edit_call["reply_markup"]
        keyboard = markup.inline_keyboard
        month_buttons = [btn.text for btn in keyboard[1]]
        assert month_buttons == ["Dec"]

    def test_month_callback_on_empty_month_shows_no_expenses_message(self) -> None:
        """Month with no expense rows shows informative text."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []
        repo.get_months_with_expenses.side_effect = lambda uid, year: {
            2026: {7},
            2025: set(),
        }.get(year, set())

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data="month:2026:3")
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        edit_call = update.callback_query.edit_message_text.call_args[1]
        assert "No expenses" in edit_call["text"]

    @pytest.mark.parametrize(
        "bad_data",
        [
            "garbage",
            "year:not-a-year",
            "month:2026",
            "month:foo:3",
            "year:",
        ],
    )
    def test_malformed_callback_data_does_not_crash(self, bad_data: str) -> None:
        """Invalid callback_data is logged and ignored without exception."""
        repo = MagicMock()
        repo.get_months_with_expenses.return_value = set()

        from expense_report.adapters.inbound.telegram_bot import _make_list_callback_handler

        handler = _make_list_callback_handler(repo)
        update = _make_callback_update(callback_data=bad_data)
        context = MagicMock()

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            # Should not raise
            asyncio.run(handler(update, context))

        update.callback_query.answer.assert_awaited_once()
        # edit_message_text should NOT be called for invalid data
        update.callback_query.edit_message_text.assert_not_awaited()


class TestDeleteHandler:
    """Tests for /delete command handler."""

    def test_delete_success_replies_with_audit_summary(self) -> None:
        """Successful /delete replies with deleted expense details."""
        from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

        mock_repo = MagicMock()
        deleted_expense = Expense(
            id=42,
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Supermarket",
            date=date(2026, 7, 10),
            category="groceries",
            user_id=12345,
            receipt_photo_id=None,
            created_at=datetime(2026, 7, 10, 12, 0, 0),
        )
        mock_repo.delete_by_id.return_value = deleted_expense

        handler = _make_delete_handler(mock_repo)
        update = _make_update(text="/delete 42")
        context = MagicMock()

        asyncio.run(handler(update, context))

        call_args = update.effective_message.reply_text.call_args
        reply = call_args[0][0]
        assert reply == "🗑️ Deleted expense #42: Supermarket — 42.50 EUR — 2026-07-10"
        mock_repo.delete_by_id.assert_called_once_with(12345, 42)

    def test_delete_not_found_replies_with_not_found_message(self) -> None:
        """Non-existent expense /delete replies with not found."""
        from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

        mock_repo = MagicMock()
        mock_repo.delete_by_id.return_value = None

        handler = _make_delete_handler(mock_repo)
        update = _make_update(text="/delete 99")
        context = MagicMock()

        asyncio.run(handler(update, context))

        reply = update.effective_message.reply_text.call_args[0][0]
        assert "Expense #99 was not found." == reply

    def test_delete_invalid_format_returns_usage(self) -> None:
        """Invalid /delete formats all return usage message."""
        from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

        mock_repo = MagicMock()
        handler = _make_delete_handler(mock_repo)

        invalid_inputs = ["/delete", "/delete abc", "/delete 42 extra"]
        for cmd in invalid_inputs:
            update = _make_update(text=cmd)
            context = MagicMock()
            asyncio.run(handler(update, context))
            reply = update.effective_message.reply_text.call_args[0][0]
            assert reply == "Usage: /delete <expense_id>", f"Failed for '{cmd}', got: {reply}"

    def test_delete_non_positive_id_returns_usage(self) -> None:
        """Non-positive ids like /delete 0 return usage."""
        from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

        mock_repo = MagicMock()
        handler = _make_delete_handler(mock_repo)

        update = _make_update(text="/delete 0")
        context = MagicMock()
        asyncio.run(handler(update, context))
        reply = update.effective_message.reply_text.call_args[0][0]
        assert reply == "Usage: /delete <expense_id>"

    def test_delete_no_effective_message_returns_silently(self) -> None:
        """Handler returns silently when effective_message is None."""
        from expense_report.adapters.inbound.telegram_bot import _make_delete_handler

        mock_repo = MagicMock()
        handler = _make_delete_handler(mock_repo)
        update = MagicMock()
        update.effective_message = None
        context = MagicMock()

        asyncio.run(handler(update, context))
        # Should not raise — just return silently


class TestMainFunction:
    """Tests for the main() entry point."""

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_token_raises_keyerror(self) -> None:
        """main() raises KeyError when TELEGRAM_BOT_TOKEN is not set."""
        from expense_report.adapters.inbound.main import main

        with pytest.raises(KeyError):
            main()
