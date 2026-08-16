# Generic Error Handling in Message Handlers — Expectations

Addresses issue #3: when an unexpected error occurs while processing a message
(LLM auth failure, database error, …), the bot currently stays silent — the
exception is only logged internally by python-telegram-bot, and the user gets
no feedback.

## Happy Path

1. **User receives a generic error message on unhandled errors.**
   - When any registered handler (photo, text, /start, /report, /list, /delete,
     list callback, delete callback) raises an unhandled exception, the user
     receives exactly one reply: the generic error message
     `⚠️ Il servizio non e' al momento disponibile. Riprova piu' tardi.`
   - The message is the exact string proposed in issue #3.

2. **The error is logged with full details including traceback.**
   - The unhandled exception is logged at ERROR level with `exc_info`, so the
     log line carries the exception type, message, and the full traceback.
   - Verified against installed python-telegram-bot 22.8: once an error handler
     is registered, PTB no longer logs the exception itself, so the handler is
     solely responsible for the log line.

3. **Callback query updates are answered before notifying.**
   - When the error happens in a callback query handler, the pending callback
     query is answered (client spinner stops) and the generic message is sent
     on the callback's message.

## Edge Cases

4. **No exception details leak to the user.**
   - The user-facing message never contains the exception class, message, or
     any traceback fragment — only the fixed generic message.

5. **Update unavailable (e.g. job callback error): log only, no crash.**
   - PTB passes `update=None` to error handlers when no Update is available.
   - The handler logs the error with traceback, logs a WARNING that the user
     cannot be notified, and does not raise.

6. **Update without an effective message: log only, no crash.**
   - If `update.effective_message` is `None` (e.g. callback with an
     inaccessible message), the handler logs a WARNING and does not raise.

7. **Failed notification does not propagate.**
   - If sending the generic message itself raises (e.g. Telegram API error),
     the failure is logged at ERROR and the handler returns without raising,
     so PTB does not log a second uncaught error from the error handler.

8. **Answering an already-answered callback query does not crash.**
   - The `query.answer()` call in the error handler is defensive: if it raises
     (e.g. the handler had already answered the callback), it is swallowed and
     logged at DEBUG, and the generic message is still sent.

## Non-Behaviors

- No per-handler `try/except` wrapping is added: the single global error
  handler covers all current and future handlers (including the authorization
  guard and any future command), which is why the factory handlers stay
  unwrapped.
- Unauthorized users are NOT notified: the authorization guard stops dispatch
  with `ApplicationHandlerStop`, which PTB does not route to error handlers.
- The domain and application layers are untouched — this is purely a Telegram
  driving-adapter concern.
- No new dependencies.

## Evidence Mapping

| Expectation | Evidence |
|-------------|----------|
| Generic message on unhandled error | `TestGlobalErrorHandler::test_error_handler_replies_with_generic_message` (pytest) |
| ERROR log with traceback | `TestGlobalErrorHandler::test_error_handler_logs_error_with_traceback` (pytest) |
| Callback answered + notified | `TestGlobalErrorHandler::test_error_handler_callback_update_answers_and_notifies` (pytest) |
| No exception detail leak | `TestGlobalErrorHandler::test_error_handler_does_not_leak_exception_details` (pytest) |
| None update: log only, no crash | `TestGlobalErrorHandler::test_error_handler_none_update_logs_and_returns` (pytest) |
| No effective message: no crash | `TestGlobalErrorHandler::test_error_handler_no_effective_message_warns_and_returns` (pytest) |
| Failed notification swallowed | `TestGlobalErrorHandler::test_error_handler_survives_failed_reply` (pytest) |
| Already-answered callback tolerated | `TestGlobalErrorHandler::test_error_handler_tolerates_failed_callback_answer` (pytest) |
| Registration on Application | `TestRegisterHandlers::test_registers_global_error_handler` (pytest), `TestMainStartsLogging::test_logging_configured_before_adapters` call-order (pytest) |
