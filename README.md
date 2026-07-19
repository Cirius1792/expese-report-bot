# Expense Report Bot

A Telegram bot that extracts structured expense data from receipt photos and free-text messages using LLM-powered extraction. Built with a hexagonal (ports & adapters) architecture.

## Features

- **Receipt photo extraction**: Send a photo of a receipt — the bot extracts amount, currency, merchant, date, and optional category
- **Free-text expense logging**: Type "lunch 15.50 eur at Mario's Pizzeria on 2026-07-10" and it's saved automatically
- **Correction loop**: If the LLM can't extract all required fields, the bot asks for missing info. You can refine up to 3 times before manual intervention is suggested
- **Monthly CSV reports**: `/report` generates a CSV with all your expenses for the current month
- **User isolation**: Each Telegram user sees only their own expenses

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
```

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
uv run pytest          # 92 unit/integration tests
uv run behave          # 15 BDD scenarios, 126 steps
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

## License

MIT
