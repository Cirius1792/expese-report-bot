# Expectations: README Tests + Coverage Badges

**Scope:** README.md + `.github/workflows/ci.yml` + `pyproject.toml` (dev deps only).
No `src/` changes. Badge URLs use the repo name exactly as `expese-report-bot`
(known upstream typo — must be preserved verbatim).

## Happy path

- **Tests badge** — README renders a live GitHub Actions status badge sourced from
  the CI workflow file (`.github/workflows/ci.yml`), via the native
  `https://github.com/<owner>/<repo>/actions/workflows/<file>.yml/badge.svg`
  URL. No third-party service.
- **Coverage badge** — README renders `coverage.svg` committed at the repo root,
  served from `https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/main/coverage.svg`.
- Badges are placed in a centered block directly below the `<h1 align="center">`
  heading, before the intro paragraph, matching the README's existing centered style.
- `unit-tests` CI job runs `uv run pytest --cov=expense_report` and uploads the
  `.coverage` file as an artifact named `coverage-data` (`include-hidden-files: true`).
- A new `generate-badge` CI job:
  - depends on `bdd-tests` (badge only advances when the **entire** CI is green),
  - runs only on `push` to `refs/heads/main` (`if:` guard — never on PR heads),
  - has `permissions: contents: write`,
  - downloads the `coverage-data` artifact, installs `coverage-badge` locally
    (`pip install coverage-badge`), runs `coverage-badge -o coverage.svg -f`,
  - commits it via `stefanzweifel/git-auto-commit-action@v4` with message
    `"docs: update coverage badge"` and `file_pattern: coverage.svg`.
- `pytest-cov` is present in the `[dependency-groups] dev` group in `pyproject.toml`.
- `coverage.svg` is **not** hand-committed on the feature branch — CI generates it
  on first push to `main`.

## Edge cases

- On PR runs, `generate-badge` is skipped entirely (no commit attempts on PR
  branches / forks).
- `coverage.svg` is force-overwritten (`-f`) on every update.
- `coverage-badge` is installed **inside** the CI job only — it is NOT a project
  dependency.
- `pytest-cov` pulls in `coverage`, which produces the `.coverage` file consumed
  by `coverage-badge`.

## Behaviors that must NOT happen

- `ci.yml` is **not** renamed; `bdd-tests` behavior is unchanged.
- No third-party coverage service (Codecov, Coveralls, …).
- README branding is untouched (logo, H1, intro — see `readme-branding.md`).
- No `coverage.svg` committed on the feature branch (D8).
- No secrets/tokens in any changed file (gitleaks enforces).
- No `src/` changes.

## Verification

```bash
# 1. Full quality gate after changes
uvx ruff format && uvx ruff check && uvx ty check && uv run pytest

# 2. Prove coverage pipeline locally (exact CI commands)
uv run pytest --cov=expense_report -q            # produces .coverage
uvx coverage-badge -o /tmp/badge-test.svg -f     # emits SVG markup
head -c 200 /tmp/badge-test.svg

# 3. Validate workflow YAML
uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"

# 4. Show diff
git diff --stat
```
