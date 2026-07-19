# ADR 0004: Stdlib Logging for Operational Observability

**Date:** 2026-07-19
**Status:** Accepted

## Context

The Expense Report Bot runs as a Docker container. Operators need visibility into bot operations (extractions, savings, corrections, retries) without adding a third-party observability stack. The bot must not leak secrets (tokens, API keys) or payloads (user text, image bytes, base64) into logs.

## Decision

### Use Python stdlib `logging` only

No new dependency. The stdlib `logging` module is sufficient for structured operational logs visible through `docker logs` / `docker compose logs`.

### Configure logging at the process entrypoint

`src/expense_report/adapters/inbound/main.py` calls `_configure_logging()` before any adapters are initialized, so all downstream modules inherit the configured root logger.

Configuration details:

| Concern | Decision |
|---------|----------|
| Log level | `LOG_LEVEL` env var, default `INFO`, invalid values fall back to `INFO` with a warning |
| Output stream | `sys.stdout` (captured by Docker log driver) |
| Format | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` |
| Force reset | `force=True` so logging is always reconfigured even if a library initialized early |

### Container visibility

`PYTHONUNBUFFERED=1` is set in the Dockerfile to prevent Python from buffering log output, ensuring Docker's log collector sees every line in real time.

### Logging levels by layer

| Layer | Level | What |
|-------|-------|------|
| Inbound (Telegram handlers) | `INFO` | User actions: `/start`, `/report`, photo/text received, extraction complete/partial/saved, correction received/resolved/maxed out |
| Inbound (Telegram handlers) | `DEBUG` | Skipped updates with no effective message or user |
| Driven (dSPy extraction) | `INFO` | Extraction/refine start and complete; amount + currency |
| Driven (dSPy extraction) | `WARNING` | LLM call retry with exception class name, attempt count |
| Driven (dSPy extraction) | `ERROR` | LLM call failed after 3 attempts |
| Driven (SQLite repo) | `INFO` | DB initialization, save (expense id + user id), query results (count per user/month) |

### What is NOT logged

- `TELEGRAM_BOT_TOKEN`, `LLM_API_KEY`, or any credential
- Full user free-text descriptions (extraction input)
- Raw image bytes or base64 image payloads
- Full conversation text or any user-identifying content beyond user_id
- Inbound adapter secrets or credential values

## Considered Options

| Option | Notes |
|--------|-------|
| **Stdlib logging (chosen)** | Zero dependencies, sufficient for Docker logs, familiar to all Python developers |
| structlog | Structured JSON logs, better for log aggregators (ELK, Datadog). Rejected: overkill for single-container deployment, adds dependency |
| loguru | Popular third-party logger, automatic format/rotation. Rejected: adds dependency, deeper integration than needed |
| No logging | Existing state. Rejected: operators cannot trace bot operations without reading source code |

## Consequences

- Operators can run `docker compose logs -f bot` and see real-time operational trace
- Debugging extraction failures is easier with retry attempt logs showing exception class names
- Logs do not contain secrets or payloads — safe to share snippets for debugging
- Adding new log statements requires only `logger = logging.getLogger(__name__)` and calls at the appropriate level
- No migration needed if a structured logging solution is added later — stdlib is the universal adapter point
