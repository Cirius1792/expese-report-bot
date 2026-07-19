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

- Behave: `features/authorization.feature` proves the authorized and unauthorized user stories via acceptance tests.
- Pytest: `tests/adapters/inbound/test_authorization.py` proves whitelist loading, missing/unreadable config handling, malformed JSON failure, invalid schema handling, audit writer formatting, audit writability checks, guard behavior, and `group=-1` registration.
- Pytest: `tests/adapters/inbound/test_logging_config.py` proves startup wiring order: logging is configured first, authorized users are loaded, the unauthorized audit is verified writable, the authorization guard is registered, and normal handlers are registered afterward.
- Full verification: `uvx ruff format`, `uvx ruff check`, `uvx ty check`, `uv run pytest`, and `uv run behave`.
