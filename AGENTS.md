<!-- FOR AI AGENTS - Human readability is a side effect, not a goal -->
<!-- Last updated: 2026-07-18 | Last verified: never -->

# AGENTS.md

**Precedence:** the **closest `AGENTS.md`** to the files you're changing wins. Root holds global defaults only.

## Commands
> Source: pyproject.toml — run all after every change; show output as evidence

| Task | Command | ~Time |
|------|---------|-------|
| Format | `uvx ruff format` | ~2s |
| Lint | `uvx ruff check` | ~3s |
| Typecheck | `uvx ty check` | ~5s |
| Test (single) | `uv run pytest tests/path/to/test.py::test_name` | ~2s |
| Test (all) | `uv run pytest` | ~30s |

> If commands fail, verify against pyproject.toml or ask user to update.

## Workflow (EDD)

1. **Before implementation** — Read `doc/adr/` for past decisions. Write expectations in `docs/expectations/<feature>.md`: happy path, edge cases, behaviors that must NOT happen. Be specific, not vague.
2. **Implement** — TDD: write failing test → implement → refactor. Stay in the hexagonal ports/adapter boundary for the layer you're touching.
3. **Prove it** — Run the **full test suite** and **paste the output**. Never say "tests pass", "should work", "all green" without the actual command output. For each expectation, show executed evidence (real inputs/outputs), not narration.
4. **Stabilize** — Critical-path expectations become automated pytest tests before the task is done.

## EDD Evidence Rules
- Evidence must be **executed**, not generative: paste actual command output, not descriptions of what you think happens.
- If a code path can't be executed in-loop (e.g., Telegram API), show the test covering it plus explicit reasoning for the gap.
- Every task ends with: (a) full `uv run pytest` output, (b) explicit mapping of expectations → evidence.

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
| `search` / `librarian` | Codebase exploration needed before handoff formulation |

## TDD Rules
- **Red first**: never write implementation before a failing test.
- Tests live in `tests/` mirroring `src/` structure.
- One assertion per test where practical; name tests as `test_<behavior>_<outcome>`.
- After every implementation change, run `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest`.

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
- Run `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest` after every change
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
- Commit secrets, tokens, or credentials
- Skip the test suite before claiming completion
- Implement without a failing test first
- Put framework or IO code in `domain/`
- Use `Any` or untyped `dict` as parameter/return types
- Say "done" without mapping expectations to executed evidence

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

## When instructions conflict
The nearest `AGENTS.md` wins. Explicit user prompts override files.
