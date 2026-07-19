# Expense Report Bot

A Telegram bot that extracts structured expense data from receipt photos and free-text messages using LLM-powered extraction. Built with a hexagonal (ports & adapters) architecture.

## Features

- **Receipt photo extraction**: Send a photo of a receipt — the bot extracts amount, currency, merchant, date, and optional category
- **Free-text expense logging**: Type "lunch 15.50 eur at Mario's Pizzeria on 2026-07-10" and it's saved automatically
- **Correction loop**: If the LLM can't extract all required fields, the bot asks for missing info. You can refine up to 3 times before manual intervention is suggested
- **Monthly CSV reports**: `/report` generates a CSV with all your expenses for the current month
- **User isolation**: Each Telegram user sees only their own expenses
- **User authorization whitelist**: Only Telegram user IDs listed in a JSON config file can interact with the bot; unauthorized attempts are silently ignored and written to `unauthorized.log`

## Prerequisites

- **Python 3.12+** (uses `X | Y` unions, PEP 695 generics)
- **uv** — package manager and tool runner ([install guide](https://docs.astral.sh/uv/getting-started/installation/))
- **Telegram Bot Token** — create a bot via [@BotFather](https://t.me/BotFather) on Telegram
- **LLM API access** — any OpenAI-compatible endpoint (see [Configuration](#configuration))

## Quick Start

```bash
# Clone and install
git clone <repo-url>
cd expense-report-bot
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your actual credentials
```

### Configuration

Create a `.env` file (or export the variables directly):

```bash
# Required
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
LLM_BASE_URL=https://api.openai.com/v1     # or your own LLM endpoint
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o                            # or any model your endpoint supports

# Optional
EXPENSE_DB_PATH=expenses.db                  # defaults to expenses.db

# Authorization
AUTHORIZED_USERS_CONFIG_PATH=authorized-users.json      # JSON whitelist of Telegram user IDs
UNAUTHORIZED_LOG_PATH=unauthorized.log                  # optional; defaults beside EXPENSE_DB_PATH
```

### Telegram user authorization

Create a whitelist JSON file before using the bot:

```json
{
  "authorized_users": ["123456789"]
}
```

Values must be numeric strings. Telegram user IDs that are not listed are silently ignored. Each unauthorized attempt appends one line to the dedicated audit file:

```text
2026-07-19T12:00:00Z user_id=987654321
```

Failure behavior:

- Missing `AUTHORIZED_USERS_CONFIG_PATH`, missing whitelist file, or unreadable whitelist file: the bot starts with no authorized users and logs a warning.
- Malformed JSON: startup fails.
- Valid JSON with invalid schema: the bot starts with no authorized users and logs a warning.
- Unwritable unauthorized audit log: startup fails.

## Usage

### Telegram Bot

```bash
uv run expense-bot
```

The bot starts polling Telegram for messages. Send it:
- A **receipt photo** — it extracts expense data and confirms with you
- **Free-form text** like `"taxi 25 usd transport"` — parsed and saved
- **`/report`** — generates a CSV of current month's expenses
- **`/start`** — welcome message with usage instructions

### CLI Extraction (for testing/scripts)

```bash
# From an image
uv run expense-extract --user-id 123 --db test.db extract-from-image receipt.jpg

# From free text
uv run expense-extract extract-from-text "lunch 15.50 eur at Mario's Pizzeria on 2026-07-10"
```

## Docker Deployment

The Compose setup uses **two separate env files** for different purposes:

| File | Purpose | Used by |
|------|---------|---------|
| `.env` | Bot runtime environment variables (`TELEGRAM_BOT_TOKEN`, `LLM_*`, `AUTHORIZED_USERS_CONFIG_PATH` etc.) | `docker-compose.yml` `env_file:` directive — injected into the running container |
| `.env.deploy` | Compose file interpolation (`${UID}`, `${GID}`) | `--env-file .env.deploy` flag — resolved at `docker compose up` time, **not** passed to the container |

```bash
# 1. Copy runtime env file (for container environment)
cp .env.example .env
# Edit .env with your real Telegram token, LLM credentials, and authorization config

# 2. Copy Compose interpolation file (for host file ownership)
cp .env.deploy.example .env.deploy
# Edit .env.deploy UID/GID if your host user is not 1000:1000

# 3. Start with both files — one for interpolation, one for the container
# Compose automatically picks up env_file: .env defined in docker-compose.yml
docker compose --env-file .env.deploy up -d
```

The container:
- Runs as the `UID:GID` specified in `.env.deploy` so the bind-mounted database is owned by the host user
- Persists the SQLite database to `./data/expenses.db` on the host
- Reads `AUTHORIZED_USERS_CONFIG_PATH` from `.env` at runtime. **In `.env`, set `AUTHORIZED_USERS_CONFIG_PATH=/data/authorized-users.json`** and place the whitelist file in `./data/` on the host. (The default from `.env.example` is a local path — Docker needs the container path.)
- Optionally set `UNAUTHORIZED_LOG_PATH=/data/unauthorized.log` in `.env` for a dedicated audit log inside the same persisted volume.
- Auto-restarts unless explicitly stopped (`restart: unless-stopped`)

**Managing the bot:**

```bash
docker compose --env-file .env.deploy logs -f   # follow logs
docker compose --env-file .env.deploy down       # stop and remove
docker compose --env-file .env.deploy up -d      # restart
docker compose --env-file .env.deploy build      # rebuild after code changes
```

## Running Tests

```bash
# Unit/integration tests (pytest)
uv run pytest

# BDD acceptance tests (Behave)
uv run behave
```

### Quality Gate

```bash
uv run ruff format     # code formatting
uv run ruff check      # linting
uv run ty check        # type checking
uv run pytest          # unit/integration tests
uv run behave          # BDD scenarios
```

## Architecture

The project follows a **hexagonal (ports & adapters)** architecture:

```
src/expense_report/
├── domain/               # Entities, value objects, domain services
│   ├── models.py         # Expense, ExtractionResult (frozen dataclasses)
│   ├── correction_state.py  # PendingCorrection, CorrectionStore
│   └── csv_generator.py  # Monthly expense CSV generation
├── ports/                # Interface definitions (Protocols/ABCs)
│   ├── extraction.py     # ExtractionPort (extract + refine)
│   └── repository.py     # ExpenseRepositoryPort (save, get, query)
└── adapters/
    ├── inbound/           # Driving adapters (entry points)
    │   ├── main.py        # Telegram bot (python-telegram-bot)
    │   ├── telegram_bot.py  # Bot handlers
    │   └── cli_extraction.py  # CLI extraction commands
    └── out/               # Driven adapters (external services)
        ├── dspy_extraction.py  # LLM extraction via dSPy
        └── sqlite_repository.py  # SQLite persistence
```

### Key Design Decisions

- **Domain has zero framework/IO imports** — frozen dataclasses only
- **dSPy backend**: Uses `ChainOfThought` with an `ExpenseSignature` for structured LLM output
- **SQLite**: Zero-config persistence, `Decimal` values stored as strings for precision
- **Correction loop**: Up to 3 refinement attempts via the same `ExtractionPort.refine` interface
- See `docs/adr/` for full Architecture Decision Records

### Dependencies

| Package | Purpose |
|---------|---------|
| `dspy-ai` | LLM extraction framework |
| `python-telegram-bot[job-queue]` | Telegram Bot API client |
| `openai` | OpenAI-compatible LLM backend |
| `pillow` | Image processing for receipt photos |

## User Stories

| # | Story | Status |
|---|-------|--------|
| 1 | Extract expense data from receipt photo | ✅ |
| 2 | Extract expense data from free-text message | ✅ |
| 3 | Send receipt photo via Telegram and get confirmation | ✅ |
| 4 | Send free-text expense via Telegram and get confirmation | ✅ |
| 5 | Extraction fails gracefully on unreadable receipt | ✅ |
| 6 | Bot prompts for missing fields on partial extraction | ✅ |
| 7 | User can correct/amend extracted fields | ✅ |
| 8 | Multiple correction retries with max attempt limit | ✅ |
| 9 | Generate monthly CSV expense report | ✅ |
| 10 | Expenses are isolated per user | ✅ |
| 11 | User authorization whitelist | ✅ |

## License

MIT
