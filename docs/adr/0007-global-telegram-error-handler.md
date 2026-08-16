# ADR 0007: Global Telegram Error Handler for User Feedback

**Date:** 2026-08-15
**Status:** Accepted

## Context

Issue #3: when an unhandled exception occurs while processing a message
(LLM authentication failure, database error, …), the bot replies with nothing.
The exception is only logged internally, and the user is left without feedback.
The unwrapped call sites were identified in the factory handlers of
`src/expense_report/adapters/inbound/telegram_bot.py` (photo, text, /report,
/list), but any future handler would have the same problem.

Verified against the installed python-telegram-bot 22.8 source
(`Application.process_error`):

- When no error handler is registered, PTB logs the exception itself
  (`"No error handlers are registered, logging exception."`).
- When an error handler **is** registered, PTB does **not** log the exception —
  the handler is solely responsible for logging.
- The handler callback signature is `async def callback(update: object | None,
  context: CallbackContext)`; `context.error` holds the exception and
  `update` may be `None` (e.g. errors in job callbacks).
- `update.effective_message` already covers `message`, `edited_message`,
  `channel_post`s and `callback_query.message` (when it is a real Message).

## Decision

Register a single **global** error handler on the `Application` via
`app.add_error_handler()`:

| Concern | Decision |
|---------|----------|
| Handler location | `handle_unexpected_error()` in `adapters/inbound/telegram_bot.py` — it is Telegram transport behavior, so it belongs in the driving adapter |
| Registration | `register_global_error_handler(app)` in `telegram_bot.py`, called from `main.py` (mirrors the `register_authorization_guard` pattern) |
| Logging | `logger.error(..., exc_info=error)` — ERROR level with the full traceback; mandatory because PTB stops logging once a handler is registered |
| User message | Fixed constant `GENERIC_ERROR_MESSAGE = "⚠️ Il servizio non e' al momento disponibile. Riprova piu' tardi."` — the exact string proposed in issue #3 |
| Callback updates | `await callback_query.answer()` first (stops the client spinner), defensively wrapped so an already-answered callback cannot block notification |
| No update / no effective message | WARNING log, graceful return — the handler never raises |
| Failed notification | `reply_text` failure caught, logged at ERROR, not propagated (PTB would otherwise log a second uncaught error) |

The exception message is logged (with traceback) but is **never** sent to the
user; only the fixed generic message is.

## Considered Options

| Option | Notes |
|--------|-------|
| Per-handler `try/except` in the four factory handlers (issue suggestion list) | Rejected: duplicates the same block in every handler, cannot cover the authorization guard, handler plumbing, or future handlers; easy to forget when adding a handler |
| **Global `add_error_handler` (chosen)** | One seam for all current and future handlers; matches PTB's intended mechanism; keeps factory handlers unwrapped and focused |
| Global handler + per-handler `try/except` | Rejected: redundant — the global handler already receives every unhandled exception |

## Consequences

- Every unhandled handler exception now produces one ERROR log line with the
  full traceback **and** exactly one generic user message (when the update
  identifies a message).
- The issue's suggested registration point (`main.py`) is honored: `main()`
  calls `register_global_error_handler(app)` after `register_handlers(...)`.
- Unauthorized users remain silent: the authorization guard stops dispatch via
  `ApplicationHandlerStop`, which PTB does not route to error handlers.
- Logging an exception message may capture small fragments of user content
  inside exception messages; this is accepted because the issue explicitly
  requires full error details for operational debugging (see ADR 0004 for the
  general no-secrets/no-payloads policy, which remains in force for our own
  log statements).
- Tests mock the PTB boundary, so behavior is pinned to the documented
  `process_error` contract (handler receives `update` possibly `None`,
  `context.error` set, PTB silent otherwise).
