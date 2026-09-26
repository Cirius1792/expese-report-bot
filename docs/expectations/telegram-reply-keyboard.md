# Feature Spec: Telegram Reply Keyboard (Bottom Action Bar)

> TrackBot-style persistent bottom bar: a 2-row grid of tappable emoji buttons
> below the input field that trigger the bot's main actions.
> Reference: https://trackbot.eu (smartphone screenshot, "Traccia / Lista / Aiuto" grid).

## Feature description

The bot shows a **custom reply keyboard** (Telegram `ReplyKeyboardMarkup`) — a
persistent bar of action buttons below the chat input field, like TrackBot's
"➕ Traccia / ☰ Lista / ? Aiuto" grid. Tapping a button sends its label as a
plain chat message (pretty chat history, no `/command` clutter), and the bot
routes the label to the matching existing command handler.

### Button set (v1, English labels)

| Row | Button | Label sent | Routes to |
|-----|--------|-----------|-----------|
| 1 | ➕ Add | `Add` | `/add` (hint prompt) |
| 1 | ☰ List | `List` | `/list` (month view + inline keyboard) |
| 1 | 📄 Report | `Report` | `/report` (CSV export) |
| 2 | ❓ Help | `Help` | `/start` (welcome message) |
| 2 | 🗑 Remove | `Remove` | `/remove` (hint prompt) |

`/delete` is intentionally NOT in the bar (it requires an argument; it stays
reachable via the `/remove` hint and the welcome text).

### Keyboard properties

- `resize_keyboard=True` (input field shrinks to make room, like TrackBot)
- `is_persistent=True` (bar stays visible; auto-shown when the chat is reopened)
- `one_time_keyboard=False` (default)
- Attached to: the `/start` (Help) reply, and the expense-recorded/updated
  confirmation replies (covers the photo-first flow where the user never
  types `/start`). With `is_persistent=True` a single attachment is enough for
  persistence; the extra attachments are belt-and-braces.

## Hexagonal architecture constraints

- **Domain: no changes.** No new entities/value objects.
- **Ports: no changes.** No new or modified port protocols. The bar is a
  transport-level presentation concern.
- **Application: no changes.** No new use cases; buttons dispatch to the
  already-existing command handlers.
- **Inbound adapter only** (`adapters/inbound/telegram_bot.py`): keyboard
  constant, label→handler routing, attachment points, welcome text tweak.
- **No new dependencies.**
- Decision recorded as **ADR 0010: Telegram Reply Keyboard** at implementation.

## Implementation plan (TDD, red-first)

All code changes in `src/expense_report/adapters/inbound/telegram_bot.py`
unless noted.

1. **Keyboard constant** — failing test on shape first:
   `REPLY_KEYBOARD: ReplyKeyboardMarkup` with the exact 2×3/2×2 grid above
   (`KeyboardButton` labels), `resize_keyboard=True`, `is_persistent=True`.
   Test asserts grid structure, labels, order, flags.
2. **Attachment at /start** — failing test: `_handle_start` replies with
   `reply_markup=REPLY_KEYBOARD`.
3. **Label routing** — failing tests per label, then implement:
   `register_handlers` constructs the command handlers once (list/report via
   existing factories; start/add/remove existing functions) and passes a
   `dict[str, handler]` label→handler map into `_make_text_handler`.
   The text handler checks an **exact, case-sensitive full-text match**
   against the map *before* calling the recording port; on a match it invokes
   the mapped handler with the same `Update`; on a miss it proceeds to
   `expense_recording.record(...)` exactly as today.
   Labels: `Add`, `List`, `Report`, `Help`, `Remove`.
4. **Attachment on recorded confirmations** — failing test:
   `_reply_with_recorded_expense` and `_reply_with_resolved_correction`
   include `reply_markup=REPLY_KEYBOARD` (inline delete button unchanged —
   the inline keyboard and the reply keyboard coexist; PTB merges them in the
   `reply_markup` via the inline markup, so attach the reply keyboard as
   `ReplyKeyboardMarkup` on the same message alongside the existing inline
   keyboard — if PTB does not allow both markups on one message, attach the
   reply keyboard to a follow-up confirmation message instead; decide from
   the failing test).
5. **Welcome text** — update `WELCOME_MESSAGE` to mention the bottom bar
   ("tap the buttons below the input field") while still advertising the
   same command set.
6. **Behave acceptance** — `features/reply_keyboard.feature` + steps:
   press-each-label stories and the free-text-not-routed story.
7. **ADR 0010** — `docs/adr/0010-telegram-reply-keyboard.md`.
8. **Full gate** — `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest && uv run behave`, output pasted as evidence.

Files touched:

| File | Change |
|------|--------|
| `src/expense_report/adapters/inbound/telegram_bot.py` | keyboard constant, routing, attachments, welcome text |
| `tests/adapters/inbound/test_telegram_bot.py` | new unit tests |
| `features/reply_keyboard.feature`, `features/steps/` | acceptance feature |
| `docs/expectations/telegram-reply-keyboard.md` | this spec (finalized) |
| `docs/adr/0010-telegram-reply-keyboard.md` | new ADR |

## Expectations

### Happy path

- After `/start`, the user sees a 2-row bottom bar with the five buttons in
  the order above, and the input field is resized.
- The bar persists: it remains after command results, after expense
  recording, after closing, and when the chat is reopened (`is_persistent`).
- Tapping `List` sends the chat text `List` (not `/list`) and produces the
  same month view (text + inline year/month keyboard) as typing `/list`.
- Tapping `Report` produces the same CSV document flow as `/report`.
- Tapping `Add` / `Remove` produce the same hint prompts as `/add` / `/remove`.
- Tapping `Help` produces the welcome message (same as `/start`), with the
  keyboard attached.
- A photo-first user (never typed `/start`) gets the bar after their first
  recorded-expense confirmation.

### Edge cases

- Free text that exactly equals a label (user deliberately types `List`) is
  routed to the command — documented, accepted collision; no crash.
- Case differs (`list`, `LIST`) → NOT routed; goes to the recording port as
  free text (existing behavior).
- A label pressed mid-correction-wizard (pending correction state): the
  command executes, the pending correction state is untouched; the next
  free-text message continues the wizard.
- Labels typed with a trailing command form (`/List`, `/list`) keep existing
  `CommandHandler` behavior (case-insensitive command matching is unchanged).
- Unauthorized users: the authorization guard (group=-1) stops the update
  before any handler — no routing, no reply, no keyboard interaction.
- Group chat: the bar is shown to all members (`selective` not set); the bot
  is intended for private, whitelisted use — documented.
- `/delete <id>`, correction, extraction, and recording flows are unchanged.

### Behaviors that must NOT happen

- No changes to `domain/`, `ports/`, or `application/` layers.
- No new dependencies.
- No new port interface, no application use case.
- Label routing must not bypass the authorization guard.
- The inline keyboards (year/month under `/list`, 🗑️ Delete under
  recorded expenses) must keep working unchanged.
- `/delete` must not be reachable from the bar and its behavior is unchanged.
- Free-text expense descriptions that do not exactly match a label must not
  be swallowed by routing.

## Verification plan

### In-loop (executed evidence)

- Pytest: markup shape; `/start` attachment; recorded-confirmation
  attachment; one routing test per label (assert same port calls and reply
  text as the `/command` path); free-text not routed (incl. lowercase `list`);
  correction-pending state preserved after label press.
- Behave: `features/reply_keyboard.feature`.
- Full gate output pasted (ruff format/check, ty, pytest, behave).

### Live on the real bot (user-driven protocol)

I run/deploy the bot; the user taps on a real Telegram client and provides a
screenshot per step; I cross-check against bot stdout logs:

1. `/start` → welcome + 2-row bar, resized input field. *(screenshot)*
2. Tap `List` → chat shows `List`, month view + inline keyboard, bar stays. *(screenshot)*
3. Tap `Report` → CSV document delivered. *(screenshot)*
4. Tap `Add`, `Remove`, `Help` → correct replies. *(screenshot)*
5. Send a receipt photo → extraction OK, bar visible. *(screenshot)*
6. Partial extraction → wizard replies, bar intact; complete it. *(screenshot)*
7. Type `lunch 15 eur` → routes to extraction, not to a command. *(screenshot)*
8. Reopen the chat after some time → bar still present. *(screenshot)*
9. Type `List` deliberately → routes to `/list` (documented collision). *(screenshot)*

### Deployment

1. Implement on a branch; full gate green.
2. Release: bump `pyproject.toml` to **0.7.0**, commit, tag `v0.7.0`, push —
   `release.yml` builds + pushes `ghcr.io/cirius1792/spencer-bot:0.7.0`
   (also `0.7`, `latest`) and opens the GitHub Release.
3. User updates the image tag in
   `~/PersonalProjects/hs-spenser-bot/docker-compose.yml`,
   `docker compose pull && docker compose up -d`.
4. User runs the live checklist; feedback loop until acceptance.
