# Expectations: Bot Operational Logging

## Happy path

- When the Telegram bot process starts, it configures Python logging before any adapters are initialized.
- Logs are written to the process standard output/stderr stream so `docker compose logs -f bot` and `docker logs expense-report-bot` can show them without extra configuration.
- `LOG_LEVEL` controls verbosity and defaults to `INFO`; invalid values fall back to `INFO` with a warning.
- Startup logs identify the configured log level and database path, but never include secret values such as Telegram tokens or LLM API keys.
- Bot handlers log each major operation at `INFO`: `/start`, `/report`, receipt photo received, free-text expense received, correction received, extraction complete/partial, expense saved, report generated/no expenses.
- Driven adapters log long-running or failure-prone operations: dSPy/text extraction, direct image extraction, retry attempts, SQLite initialization, save, and report queries.

## Edge cases

- Updates missing an effective message or user are logged at `DEBUG` and skipped without raising.
- Partial extraction logs list only missing field names, not raw receipt bytes or full user text.
- LLM retry logging includes attempt counts and exception class/name, but does not include source payloads or credentials.
- Docker runtime defaults do not buffer logs in a way that hides them from container log collectors.

## Behaviors that must NOT happen

- The bot must not use `print` for operational logs.
- The bot must not log `TELEGRAM_BOT_TOKEN`, `LLM_API_KEY`, raw image bytes, base64 image payloads, or full free-text expense descriptions.
- The domain layer must not import or configure logging.
- Logging configuration must not require a new external dependency.
