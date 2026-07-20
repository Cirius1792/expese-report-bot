# CI Pipeline Design

**Date:** 2026-07-20  
**Status:** approved

## Goal

Set up a GitHub Actions CI pipeline that runs the full unit test suite and the full Behave BDD test suite on every push to `main` and every pull request.

## Scope

- **In:** pytest (142 tests) + behave (17 scenarios)
- **Out:** linting, formatting, type-checking (stays local per AGENTS.md workflow), deployment, Docker builds

## Triggers

- Push to `main`
- Pull request opened/updated against `main`

## Architecture

Two jobs in sequence — `unit-tests` runs first, and `bdd-tests` runs only if it passes (fail-fast via `needs`).

```
push to main / PR opened
       │
       ▼
  ┌─────────────┐
  │ unit-tests   │  → uv sync --dev --frozen → uv run pytest
  └──────┬──────┘
         │ (if pass)
         ▼
  ┌─────────────┐
  │ bdd-tests    │  → uv sync --dev --frozen → uv run behave
  └─────────────┘
```

Sequential because failing unit tests almost always mean BDD tests will also fail — no point burning CI minutes.

## Workflow file

Location: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --dev --frozen
      - name: Run unit tests
        run: uv run pytest

  bdd-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: uv sync --dev --frozen
      - name: Run BDD tests
        run: uv run behave
```

## Design decisions

- **`astral-sh/setup-uv@v5`** — official Astral action, installs uv + Python in one step, no separate `actions/setup-python` needed
- **`--frozen`** — prevents any dependency drift from `uv.lock`, ensures CI runs exactly what's committed
- **`--dev`** — pulls in pytest, behave, and pre-commit from the `dev` dependency group
- **No caching** — dependencies are ~20MB; `uv sync` is fast enough without cache overhead for this project size
- **Single Python version (3.12)** — single-project repo, no library publishing constraints; a matrix can be added later if needed

## Test isolation

Both test suites mock external boundaries:
- **pytest** mocks dspy via `conftest.py`
- **Behave** mocks dspy + python-telegram-bot via `environment.py`

No API keys, network access, or external services are required — the pipeline runs fully self-contained.

## Out of scope

- Ruff format/check and ty typecheck in CI (AGENTS.md already mandates these locally before every commit)
- Docker image build/push
- Deployment to any environment
- Python version matrix
- Coverage reporting
