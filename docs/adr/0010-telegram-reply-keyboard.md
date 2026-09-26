# ADR 0010: Telegram Reply Keyboard (Bottom Action Bar)

**Date:** 2026-09-26
**Status:** Accepted

## Context

Issue #14 asks for a persistent reply keyboard (a TrackBot-style bottom action
bar) attached to the `/start`/Help reply and to the confirmation replies after
an expense is recorded or updated. The recorded/updated confirmation already
carries an inline keyboard with a per-expense `🗑️ Delete` button (ADR 0006).

The Bot API's `sendMessage` accepts a single `reply_markup` object, so one
message cannot carry both an `InlineKeyboardMarkup` and a
`ReplyKeyboardMarkup` at the same time.

## Decision

- The confirmation message keeps its inline delete keyboard unchanged.
- A lightweight follow-up message is sent immediately after the confirmation,
  carrying only the `ReplyKeyboardMarkup` (hint text: "Tap the buttons below
  the input field to continue.").
- On the `/start`/Help path the reply keyboard is attached directly to the
  welcome message, since nothing competes for its `reply_markup`.

## Considered Alternatives

- **Replace the inline delete button with the reply keyboard.** Rejected:
  the inline button is the per-expense delete affordance; the reply keyboard
  cannot target a specific expense ID.
- **Drop the inline button and rely on `/delete` only.** Rejected: removes a
  primary UX element of the record flow.
- **Two separate confirmation flows with different buttons.** Rejected:
  duplicates the confirmation code path and confuses users.

## Consequences

- A recorded/updated expense confirmation is now two messages (summary +
  action bar) instead of one.
- Because `is_persistent=True`, Telegram keeps the keyboard for the whole chat
  after the first attachment; the follow-up is cheap and keeps one code path
  for every confirmation.
- Test helpers that inspect "the last reply" (`get_last_reply`, the exact
  button set step) must skip the keyboard-only follow-up.
