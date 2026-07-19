# Telegram User Authorization Design

**Date:** 2026-07-19
**Status:** Approved for implementation planning

## User story

As the bot owner, I want the Telegram bot to accept messages only from whitelisted Telegram user IDs, so that unauthorized users cannot interact with the bot and every unauthorized attempt is recorded for audit.

## BDD acceptance scope

Create `features/authorization.feature` with two initial scenarios focused on the authorization boundary:

1. **Authorized user can send a free-text expense message**
   - Given the bot authorization whitelist contains my Telegram user ID
   - When I send a free-text expense message
   - Then the bot sends a reply

2. **Unauthorized user is silently ignored and logged**
   - Given the bot authorization whitelist does not contain my Telegram user ID
   - When I send a free-text expense message
   - Then the bot sends no reply
   - And the unauthorized attempts log contains my Telegram user ID
   - And the unauthorized attempts log contains an ISO-8601 UTC timestamp ending in `Z`

The authorized scenario proves the user is not blocked. The unauthorized scenario proves silent ignore plus audit logging. These scenarios intentionally avoid asserting expense persistence or LLM invocation because the story is about access control.

## Architecture

Authorization lives in the Telegram inbound adapter layer. It must not be placed in the domain layer because it depends on Telegram `Update` objects, Telegram user IDs, PTB dispatching, JSON configuration, and filesystem audit logging.

Use the python-telegram-bot native guard pattern:

- Register a `TypeHandler(Update, authorization_guard)` before normal handlers using `group=-1`.
- If `update.effective_user.id` is authorized, the guard returns normally and downstream handlers continue.
- If the user is unauthorized, the guard writes one audit line and raises `ApplicationHandlerStop` so no command, text, photo, report, correction, or future handler sees the update.

This follows the PTB design-pattern recommendation for limiting who can use a bot and is preferred over wrapping each callback or adding `filters.User` to every handler.

## Components

### Authorized users loader

Reads the whitelist JSON from `AUTHORIZED_USERS_CONFIG_PATH` once during startup.

Expected schema:

```json
{
  "authorized_users": ["123456789", "987654321"]
}
```

Rules:

- The key is `authorized_users`.
- Values are numeric strings only.
- Telegram authorization is based on `update.effective_user.id`, not chat ID.
- Config changes require bot restart.

### Authorization guard

Checks `update.effective_user.id` against the loaded whitelist.

Behavior:

- Authorized user: return normally.
- Unauthorized user with user ID: append audit line and raise `ApplicationHandlerStop`.
- Update with no `effective_user`: stop propagation silently without writing a fake user ID; optionally debug-log to normal application logs.

### Unauthorized attempt audit writer

Writes a dedicated plain-text audit file. It is not the standard application log.

Log path resolution:

- If `UNAUTHORIZED_LOG_PATH` is set, use it.
- Otherwise default to `unauthorized.log` in the same directory as `EXPENSE_DB_PATH`.

Line format:

```text
2026-07-19T12:00:00Z user_id=123456789
```

Timestamps are UTC ISO-8601 seconds precision with a trailing `Z`.

### Startup wiring

`src/expense_report/adapters/inbound/main.py` should:

1. Configure normal application logging as it does today.
2. Resolve `EXPENSE_DB_PATH`.
3. Load authorized users from `AUTHORIZED_USERS_CONFIG_PATH`.
4. Resolve and verify the unauthorized audit log path.
5. Register the authorization guard in `group=-1`.
6. Register the existing bot handlers normally.

Existing `/start`, `/report`, photo, text, and correction handlers should remain focused on expense behavior and should not each contain whitelist checks.

## Configuration and failure modes

Environment variables:

```bash
AUTHORIZED_USERS_CONFIG_PATH=/path/to/authorized-users.json
UNAUTHORIZED_LOG_PATH=/path/to/unauthorized.log
EXPENSE_DB_PATH=/path/to/expenses.db
```

Failure rules:

- Missing `AUTHORIZED_USERS_CONFIG_PATH`: bot starts, emits warning to normal app logs, authorized set is empty.
- Whitelist path missing or unreadable: bot starts, emits warning to normal app logs, authorized set is empty.
- Malformed JSON: bot startup fails.
- Valid JSON with invalid schema, including missing `authorized_users`, non-list value, or entries that are not numeric strings: bot starts, emits warning to normal app logs, authorized set is empty.
- Unauthorized audit file cannot be created or written: bot startup fails.

Runtime rules:

- Authorized user proceeds normally and no unauthorized audit line is written.
- Unauthorized user receives no reply, downstream handlers do not run, and one audit line is appended.
- Authorization applies globally to `/start`, `/report`, free-text expenses, receipt photos, correction replies, and future Telegram handlers.

## Testing plan

### Behave

Add `features/authorization.feature` with the two acceptance scenarios described above.

### Pytest

Cover critical behavior with unit/integration tests:

- Config loader loads valid numeric-string user IDs.
- Missing env/path/unreadable file returns an empty authorized set and logs a warning.
- Malformed JSON raises a startup-blocking error.
- Invalid schema returns an empty authorized set and logs a warning.
- Unauthorized audit writer writes exactly one plain-text line per attempt.
- Audit timestamps use UTC ISO-8601 format ending in `Z`.
- Startup verification fails if the audit file cannot be created or written.
- Authorization guard returns normally for authorized users.
- Authorization guard logs and raises `ApplicationHandlerStop` for unauthorized users.
- Authorization guard stops updates with no `effective_user` without writing a misleading `user_id`.
- Main wiring registers the guard in `group=-1` before normal handlers.

### EDD expectations

Before implementation, create `docs/expectations/authorization.md` covering happy path, edge cases, prohibited behaviors, and evidence mapping.

### Verification commands

Implementation completion must include actual output from:

```bash
uvx ruff format
uvx ruff check
uvx ty check
uv run pytest
uv run behave
```

## Source notes from spike

The design is based on a documentation spike of python-telegram-bot v21 patterns:

- PTB design-patterns wiki recommends a high-priority guard handler for limiting bot usage.
- `Application.add_handler(..., group=...)` controls dispatch priority; lower group numbers run first.
- `TypeHandler(Update, ...)` can intercept all update types.
- `ApplicationHandlerStop` prevents later handler groups from processing the update.
- `filters.User` is useful for per-handler filtering but is not preferred here because audit logging and future-handler coverage would be easier to miss.

## Self-review notes

- Scope is one authorization feature, not a broader permissions system.
- The design keeps Telegram/framework/filesystem concerns out of the domain layer.
- The BDD scenarios are intentionally narrow and match the clarified story.
- Failure behavior is explicit for missing config, malformed JSON, invalid schema, and audit-log write failure.
