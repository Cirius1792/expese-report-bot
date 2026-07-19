# Expectations: Telegram User Authorization

## Happy path

- When a Telegram user's `effective_user.id` is present in the loaded whitelist, the authorization guard allows the update to continue to the existing bot handlers.
- Authorized users can send a free-text expense message and receive a normal bot reply.
- Authorized interactions do not write to `unauthorized.log`.

## Edge cases

- If the whitelist config env var is missing, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the whitelist file is missing or unreadable, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the whitelist file contains malformed JSON, startup fails.
- If the whitelist file contains valid JSON with an invalid schema, the bot starts with an empty authorized set and emits a warning to normal application logs.
- If the unauthorized audit file cannot be created or written, startup fails.
- Updates with no `effective_user` are stopped silently and do not write a misleading `user_id` audit line.

## Behaviors that must NOT happen

- Unauthorized users must not receive any bot reply.
- Unauthorized updates must not reach text, photo, command, report, correction, extraction, or persistence handlers.
- The domain layer must not import Telegram, JSON configuration, or filesystem audit logging code.
- The audit file must not contain message text, photo IDs, usernames, chat IDs, credentials, or LLM payloads.
- The whitelist must not authorize numeric JSON values; entries must be numeric strings.

## Evidence mapping

- **Task 1 (current):** Behave — `features/authorization.feature` proves the authorized and unauthorized user stories via acceptance tests. The production code implements `UnauthorizedAttemptAudit.record()` and `make_authorization_guard()` only. Whitelist loading, configuration env-var/file edge cases, guard registration into the PTB dispatcher, and full startup wiring are **not yet implemented** — these are covered by later tasks.
- **Task 2+ (future):** Pytest — `tests/adapters/inbound/test_authorization.py` will prove loader, audit writer, guard, and registration edge cases. Does not exist yet.
- **Task 3+ (future):** Pytest — `tests/adapters/inbound/test_logging_config.py` proves general logging startup wiring in `main()` (LOG_LEVEL env var handling, logging-before-adapter order). Authorization-specific startup wiring (empty whitelist warnings, malformed JSON failures, audit path creation failures) is **not yet covered** — these will be added in later tasks.
- Full verification: `uvx ruff format`, `uvx ruff check`, `uvx ty check`, `uv run pytest`, and `uv run behave`.
