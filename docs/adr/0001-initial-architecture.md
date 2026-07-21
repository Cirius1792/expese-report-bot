# ADR 0001: Initial Architecture

**Date:** 2026-07-18
**Status:** Accepted

## Context

Expense Report Bot is a new project. It will be a Telegram bot (initially), with possible future expansion to Slack and Teams.

## Decision

### Hexagonal Architecture (Ports & Adapters)

```
src/expense_report/
  domain/       → Entities, value objects, domain services (zero framework/IO deps)
  ports/        → Protocol definitions for all external interactions
  adapters/
    in/         → Driving adapters: input channels (Telegram, future Slack/Teams)
    out/        → Driven adapters: external services (DB, Telegram API)
```

### Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12+ | Modern syntax (X \| Y unions, PEP 695) |
| Package manager | uv | Fast, Astral ecosystem |
| Formatter/Linter | ruff | Same ecosystem, fast |
| Type checker | ty | 10-100x faster than mypy/pyright, Astral ecosystem |
| Test runner | pytest | Standard, rich plugin ecosystem |
| License | MIT | Permissive, open-source standard |
| CI | GitHub Actions | Ubiquitous, free for public repos |

### Development Methodology

- **TDD**: Red-green-refactor, never write implementation before a failing test
- **EDD**: Expectations written in `docs/expectations/`, proven with executed evidence after every task
- **Subagent delegation**: Main agent is an orchestrator, not an executor. Multi-step tasks are captured via `handoff` skill into a self-contained story, then delegated to a `worker` subagent in spawn mode. Supporting subagents (`oracle`, `reviewer`, `search`/`librarian`) provide design review, code audit, and exploration around the delegation loop
- **ADRs**: All meaningful design decisions recorded in `docs/adr/`

## Consequences

- Domain layer must have zero imports from frameworks, IO, or adapters
- Driven Adapters implement driven port Protocols; driving Adapters consume application-owned driving Interfaces, as clarified by ADR 0006
- New external integrations (Slack, Teams) translate their transport into existing driving Interfaces
