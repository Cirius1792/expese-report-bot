# ADR 0005: Telegram User Authorization Guard

**Date:** 2026-07-19
**Status:** Accepted

## Context

The bot must reject Telegram updates from users that are not present in an operator-managed whitelist. Unauthorized users must be silently ignored, and each unauthorized attempt must be appended to a dedicated plain-text audit file with timestamp and Telegram user ID.

The project uses python-telegram-bot v21 style APIs. Existing handlers are registered for `/start`, `/report`, receipt photos, free-text expenses, and correction replies.

## Decision

Use a python-telegram-bot `TypeHandler(Update, authorization_guard)` registered with `group=-1` as a global authorization gate.

The guard checks `update.effective_user.id` against the loaded whitelist:

- authorized user: return normally so later handler groups can process the update;
- unauthorized user: append one audit line and raise `ApplicationHandlerStop`;
- update with no effective user: raise `ApplicationHandlerStop` without writing an audit line.

## Consequences

- Authorization is centralized and applies to commands, text messages, photos, correction replies, and future Telegram handlers.
- Existing expense handlers stay focused on expense behavior and do not duplicate whitelist checks.
- The domain layer remains independent of Telegram, JSON configuration, and filesystem audit logging.
- Tests must include PTB mocks for `TypeHandler` and `ApplicationHandlerStop` because unit and Behave tests mock the Telegram package boundary.
