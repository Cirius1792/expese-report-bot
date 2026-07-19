"""Tests for operational logging in Telegram bot handlers.

Verifies that major bot operations produce appropriate log messages
without leaking secrets or payloads.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from expense_report.domain.correction_state import CorrectionStore, PendingCorrection
from expense_report.domain.models import ExtractionResult


# Configure logging for tests that verify log output
@pytest.fixture(autouse=True)
def _setup_logging() -> None:
    """Ensure root logger is configured for caplog tests."""
    logging.basicConfig(level=logging.DEBUG, force=True)


def _make_update(
    user_id: int = 12345,
    text: str | None = None,
    photo_file_id: str | None = None,
    effective_message: object = None,
) -> MagicMock:
    """Create a mock Telegram Update."""
    update = MagicMock()
    if effective_message is False:
        update.effective_message = None
    else:
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


def _make_context(image_bytes: bytes = b"fake-image-data") -> MagicMock:
    """Create a mock CallbackContext."""
    context = MagicMock()
    mock_file = MagicMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=image_bytes)
    context.bot.get_file = AsyncMock(return_value=mock_file)
    return context


class TestStartHandlerLogging:
    """Verify /start handler produces operational logs."""

    def test_start_handler_logs_user_id(self, caplog: pytest.LogCaptureFixture) -> None:
        """Handler logs user_id at INFO when processing /start."""
        from expense_report.adapters.inbound.telegram_bot import _handle_start

        caplog.set_level(logging.INFO)
        update = _make_update(user_id=98765)
        context = MagicMock()

        asyncio.run(_handle_start(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        user_id_strs = [
            r.message for r in records if "98765" in r.message and "start" in r.message.lower()
        ]
        assert len(user_id_strs) >= 1, (
            f"No INFO log with user_id 98765 and 'start' found. "
            f"Captured: {[r.message for r in records]}"
        )

    def test_start_handler_skip_no_message_debug(self, caplog: pytest.LogCaptureFixture) -> None:
        """Skipping update with no effective_message logs at DEBUG."""
        from expense_report.adapters.inbound.telegram_bot import _handle_start

        caplog.set_level(logging.DEBUG)
        update = _make_update(effective_message=False)
        context = MagicMock()

        asyncio.run(_handle_start(update, context))

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1, (
            f"No DEBUG log for skipped update found. "
            f"Captured: {[r.message for r in caplog.records]}"
        )
        # Should mention missing or None message
        assert any(
            "skip" in r.message.lower()
            or "no message" in r.message.lower()
            or "none" in r.message.lower()
            for r in debug_records
        )


class TestReportHandlerLogging:
    """Verify /report handler produces operational logs."""

    def test_report_handler_logs_user_request(self, caplog: pytest.LogCaptureFixture) -> None:
        """Handler logs user requested report at INFO."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update(user_id=55555)
        context = MagicMock()

        caplog.set_level(logging.INFO)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        # Should log something about the report request
        info_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in info_records)
        assert "report" in messages.lower() or "no expenses" in messages.lower()

    def test_report_handler_logs_no_expenses(self, caplog: pytest.LogCaptureFixture) -> None:
        """Handler logs 'no expenses' at INFO when no expenses found."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = []

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update(user_id=12345)
        context = MagicMock()

        caplog.set_level(logging.INFO)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "no expenses" in messages.lower()

    def test_report_handler_logs_generated(self, caplog: pytest.LogCaptureFixture) -> None:
        """Handler logs report generated with count at INFO."""
        repo = MagicMock()
        repo.get_by_user_and_month.return_value = [
            MagicMock(
                id="e1",
                amount=Decimal("10.00"),
                currency="EUR",
                merchant="Shop A",
                date=date(2026, 7, 1),
                category="food",
                user_id=12345,
                receipt_photo_id=None,
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            )
        ]

        from expense_report.adapters.inbound.telegram_bot import (
            _make_report_handler,
        )

        handler = _make_report_handler(repo)
        update = _make_update(user_id=12345)
        context = MagicMock()

        caplog.set_level(logging.INFO)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        assert "generated" in messages.lower() or "expense" in messages.lower()


class TestPhotoHandlerLogging:
    """Verify photo handler produces operational logs."""

    def test_photo_handler_logs_received(self, caplog: pytest.LogCaptureFixture) -> None:
        """Photo handler logs photo received at INFO."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("42.50"),
            currency="EUR",
            merchant="Supermarket",
            date=date(2026, 7, 15),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(user_id=12345, photo_file_id="photo-abc")
        context = _make_context()

        caplog.set_level(logging.DEBUG)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        all_messages = " ".join(r.message for r in caplog.records)
        assert "photo" in messages.lower() or "receipt" in messages.lower()
        assert "photo-abc" not in all_messages
        assert "Supermarket" not in all_messages

    def test_photo_handler_logs_partial_extraction(self, caplog: pytest.LogCaptureFixture) -> None:
        """Photo handler logs partial extraction with missing fields at INFO."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("15.00"),
            currency=None,
            merchant=None,
            date=None,
            category=None,
        )
        repo = MagicMock()
        store = CorrectionStore()

        from expense_report.adapters.inbound.telegram_bot import (
            _make_photo_handler,
        )

        handler = _make_photo_handler(adapter, repo, store)
        update = _make_update(user_id=12345, photo_file_id="photo-partial")
        context = _make_context()

        caplog.set_level(logging.INFO)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 15, 12, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        # Should mention missing or partial in the log
        assert (
            "partial" in messages.lower()
            or "missing" in messages.lower()
            or "incomplete" in messages.lower()
        )


class TestTextHandlerLogging:
    """Verify text handler produces operational logs."""

    def test_text_handler_logs_received(self, caplog: pytest.LogCaptureFixture) -> None:
        """Text handler logs text received at INFO."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        source_text = "coffee 12.50 usd"
        update = _make_update(user_id=12345, text=source_text)
        context = MagicMock()

        caplog.set_level(logging.DEBUG)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        all_messages = " ".join(r.message for r in caplog.records)
        assert (
            "text" in messages.lower()
            or "message" in messages.lower()
            or "expense" in messages.lower()
        )
        assert source_text not in all_messages
        assert "Coffee Shop" not in all_messages

    def test_text_handler_logs_saved_expense(self, caplog: pytest.LogCaptureFixture) -> None:
        """Text handler logs saved expense at INFO when extraction is complete."""
        adapter = MagicMock()
        adapter.extract.return_value = ExtractionResult(
            amount=Decimal("12.50"),
            currency="USD",
            merchant="Coffee Shop",
            date=date(2026, 7, 20),
            category="food",
        )
        repo = MagicMock()
        store = CorrectionStore()

        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        handler = _make_text_handler(adapter, repo, store)
        source_text = "coffee 12.50 usd"
        update = _make_update(user_id=12345, text=source_text)
        context = MagicMock()

        caplog.set_level(logging.DEBUG)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        all_messages = " ".join(r.message for r in caplog.records)
        assert "saved" in messages.lower() or "save" in messages.lower()
        assert source_text not in all_messages
        assert "Coffee Shop" not in all_messages

    def test_text_handler_logs_no_user_or_message_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Text handler logs DEBUG when effective_message is None."""
        from expense_report.adapters.inbound.telegram_bot import (
            _make_text_handler,
        )

        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()

        handler = _make_text_handler(adapter, repo, store)
        update = _make_update(effective_message=False)
        context = MagicMock()

        caplog.set_level(logging.DEBUG)
        asyncio.run(handler(update, context))

        debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(debug_records) >= 1


class TestCorrectionLogging:
    """Verify correction flow produces operational logs."""

    def test_correction_flow_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Correction flow (pending + refine complete) logs at INFO."""
        adapter = MagicMock()
        repo = MagicMock()
        store = CorrectionStore()

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
        correction_text = "Cafe EUR 15"
        update = _make_update(user_id=12345, text=correction_text)
        context = MagicMock()

        caplog.set_level(logging.DEBUG)

        with patch("expense_report.adapters.inbound.telegram_bot.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 7, 20, 14, 0, 0)
            asyncio.run(handler(update, context))

        records = [r for r in caplog.records if r.levelno >= logging.INFO]
        messages = " ".join(r.message for r in records)
        all_messages = " ".join(r.message for r in caplog.records)
        # Should log something about correction or refine
        assert (
            "correction" in messages.lower()
            or "refine" in messages.lower()
            or "updated" in messages.lower()
        )
        assert correction_text not in all_messages
        assert "Cafe" not in all_messages
