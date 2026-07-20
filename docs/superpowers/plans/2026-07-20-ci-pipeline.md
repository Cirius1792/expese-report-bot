# CI Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub Actions CI workflow that runs pytest then behave on every push to main and every PR.

**Architecture:** Single workflow file with two sequential jobs — unit-tests runs first, bdd-tests runs only if unit-tests passes (fail-fast via `needs`).

**Tech Stack:** GitHub Actions, astral-sh/setup-uv@v5, Python 3.12, uv

## Global Constraints

- Python version: 3.12 (per pyproject.toml `requires-python = ">=3.12"`)
- Package manager: uv with `--frozen` flag
- Dev dependency group includes pytest, behave, pre-commit
- Workflow triggers: push to main, pull_request to main
- No lint/typecheck/format in CI
- Unit tests must pass before BDD tests run

---

### Task 1: Create CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: none (first task)
- Produces: `.github/workflows/ci.yml` — CI workflow with `unit-tests` and `bdd-tests` jobs

- [ ] **Step 1: Create the CI workflow file**

```bash
mkdir -p .github/workflows
```

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

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))" && echo "YAML valid"
```

- [ ] **Step 3: Verify GitHub Actions workflow validity (optional, requires `act` or online validator)**

Run: skip if `act` not installed — GitHub's own parser will validate on push.

- [ ] **Step 4: Stage and commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions workflow for pytest + behave"
```

- [ ] **Step 5: Push to trigger CI**

```bash
git push
```
