<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Last updated: 2026-07-18 | Last verified: never -->

# AGENTS.md

**Precedence:** the **closest `AGENTS.md`** to the files you're changing wins. Root holds global defaults only.

## Commands
> Source: pyproject.toml — run all after every change; show output as evidence

> Note: `uv run pytest` runs the hermetic **unit** suite; the Liquibase-dependent **integration** tests are opted in with `-o addopts="" -m integration`, and `-o addopts=""` runs everything (ADR 0014).

| Task | Command | ~Time |
|------|---------|-------|
| Format | `uvx ruff format` | ~2s |
| Lint | `uvx ruff check` | ~3s |
| Typecheck | `uvx ty check` | ~5s |
| Test (single) | `uv run pytest tests/path/to/test.py::test_name` | ~2s |
| Test (unit) | `uv run pytest` | ~12s |
| Test (integration) | `uv run pytest -o addopts="" -m integration` | ~20s |
| Test (all) | `uv run pytest -o addopts=""` | ~30s |

> If commands fail, verify against pyproject.toml or ask user to update.

## Pre-commit Hooks

**Gitleaks** scans every commit for secrets (API keys, tokens, passwords).

```bash
uv run pre-commit install    # MANDATORY one-time setup — blocks commits with secrets
```

Config: `.pre-commit-config.yaml` (framework), `.gitleaks.toml` (allowlist).
If `pre-commit install` hasn't been run, stop and run it before any other work.

## Workflow (EDD)

1. **Before implementation** — Read `doc/adr/` for past decisions. Write expectations in `docs/expectations/<feature>.md`: happy path, edge cases, behaviors that must NOT happen. Be specific, not vague.
2. **Implement** — TDD: write failing test → implement → refactor. Stay in the hexagonal ports/adapter boundary for the layer you're touching.
3. **Prove it** — Run the **full test suite** and **paste the output**. Never say "tests pass", "should work", "all green" without the actual command output. For each expectation, show executed evidence (real inputs/outputs), not narration.
4. **Stabilize** — Critical-path expectations become automated pytest tests before the task is done.

## EDD Evidence Rules
- Evidence must be **executed**, not generative: paste actual command output, not descriptions of what you think happens.
- If a code path can't be executed in-loop (e.g., Telegram API), show the test covering it plus explicit reasoning for the gap.
- Every task ends with: (a) full `uv run pytest -o addopts=""` output, (b) explicit mapping of expectations → evidence.

## Subagent Delegation (Divide & Conquer)

The main agent is an **orchestrator**. For any task requiring multi-step work:

1. **Discuss & decide** — Agree approach, read `docs/adr/`, clarify scope. One question at a time.
2. **Capture context** — Use the `handoff` skill to produce `handoff.md`: goal, decisions made, files involved, boundaries, next steps. This bridges the spawn-mode gap — subagents don't receive session context.
3. **Formulate the story** — From the handoff, write a self-contained brief with acceptance criteria, hexagonal layer boundaries, EDD expectations to prove, and the exact verification command.
4. **Delegate in spawn mode** — Pass the story to a `worker` subagent. It returns only evidence + summary.
5. **Review** — Challenge evidence, iterate or accept.

### Supporting subagents
| Subagent | When |
|----------|------|
| `oracle` | Architecture/design unclear — consult before writing the handoff |
| `reviewer` | After worker completes — independent audit of the diff |
| `search` / `librarian` | Codebase exploration before handoff formulation |
| `worker` | External research spikes (library comparisons, docs lookup, API references) — delegate, don't research inline |

## TDD Rules
- **Red first**: never write implementation before a failing test.
- Tests live in `tests/` mirroring `src/` structure.
- One assertion per test where practical; name tests as `test_<behavior>_<outcome>`.
- After every implementation change, run `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest -o addopts=""`.

## File Map
```
src/expense_report/
  domain/           → Entities, value objects, domain services (no deps on adapters)
  ports/            → Interface definitions (protocols/ABCs) for all external actors
  adapters/
    in/             → Driving adapters (Telegram bot, future Slack/Teams)
    out/            → Driven adapters (DB, Telegram API client)
tests/              → Mirror of src/ structure
docs/
  expectations/     → EDD expectation files, one per feature
  adr/              → Architecture Decision Records, numbered (0001-title.md)
```

## Golden Samples
| For | Reference | Key patterns |
|-----|-----------|--------------|
| Port definition | `src/expense_report/ports/` | Protocol classes, narrow interfaces |
| Domain entity | `src/expense_report/domain/` | Frozen dataclasses, no framework imports |
| Adapter | `src/expense_report/adapters/` | Implements port protocol, dependency injection |

## Key Decisions
> Load `docs/adr/` at session start. Record every meaningful design choice as a new numbered ADR.

## Boundaries

### Always Do
- **Ensure pre-commit is installed** (`uv run pre-commit install`). If missing, install it first.
- Run `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest -o addopts=""` after every change
- Paste actual command output as evidence — never paraphrase test results
- Write expectations before implementation
- Follow hexagonal boundaries: domain has zero framework/IO imports
- Strong typing on all function signatures and class attributes
- Record design decisions in `doc/adr/NNNN-title.md`
- Read `doc/adr/` at the start of every session
- Ask questions one at a time, with concise reasoning

### Ask First
- Adding dependencies (`uv add`)
- Modifying GitHub Actions workflows
- Changing port interfaces (they affect all adapters)
- Repo-wide refactoring

### Never Do
- Commit secrets, tokens, or credentials — **gitleaks pre-commit hook blocks these**
- Bypass the pre-commit hook with `--no-verify` or `SKIP=gitleaks`
- Skip the test suite before claiming completion
- Implement without a failing test first
- Put framework or IO code in `domain/`
- Use `Any` or untyped `dict` as parameter/return types
- Say "done" without mapping expectations to executed evidence
- Research external libraries/docs yourself — delegate to a `worker` subagent with a self-contained brief

## Project Facts
- **Language:** Python 3.12+ (use `X | Y` unions, PEP 695 generics)
- **Package manager:** uv (`uv add`, `uv sync`, `uv run`)
- **Formatter/Linter:** ruff
- **Type checker:** ty (Astral)
- **Test runner:** pytest
- **License:** MIT
- **CI:** GitHub Actions
- **Architecture:** Hexagonal (ports & adapters)
- **Initial adapter:** Telegram bot (in), Telegram Bot API (out)

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues. Use the `gh` CLI for all operations. See `docs/agents/issue-tracker.md`.

### Triage labels

All five canonical labels use their default names: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context repo. `CONTEXT.md` and `docs/adr/` at the repo root (not yet created — created lazily by `grill-with-docs`). See `docs/agents/domain.md`.

## When instructions conflict
The nearest `AGENTS.md` wins. Explicit user prompts override files.


<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
