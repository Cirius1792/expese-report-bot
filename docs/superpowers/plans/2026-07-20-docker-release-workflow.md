# Docker Release Workflow + Release Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a tag-triggered GitHub Actions workflow that builds and pushes the spencer-bot Docker image to ghcr.io, plus a release skill for AI agents.

**Architecture:** Two files — a 4-job release workflow (validate-version → tests → build-push → github-release) and a release skill document. These are independent deliverables that can be implemented and reviewed separately.

**Tech Stack:** GitHub Actions, docker/metadata-action (semver), docker/build-push-action, softprops/action-gh-release, uv

## Global Constraints

- Registry: `ghcr.io`
- Image name: `ghcr.io/<owner>/spencer-bot` (uses `${{ github.repository_owner }}`)
- Trigger: push of semver tags matching `v*`
- Version validation: tag (minus `v` prefix) must equal `pyproject.toml` `version` field
- Docker tags on semver: `{{version}}`, `{{major}}.{{minor}}`, `latest` (except pre-releases)
- Tests must pass before image build: `uv sync --dev --frozen && uv run pytest && uv run behave`
- GitHub Release with auto-generated notes using `generate_release_notes: true`
- Release skill lives in `.agents/skills/release/SKILL.md`

---

### Task 1: Release workflow

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: none (first task)
- Produces: `.github/workflows/release.yml` with four jobs: `validate-version`, `tests`, `build-push`, `github-release`

- [ ] **Step 1: Create the release workflow file**

```bash
mkdir -p .github/workflows
```

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository_owner }}/spencer-bot

jobs:
  validate-version:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate tag matches pyproject.toml version
        run: |
          TAG_VERSION="${GITHUB_REF#refs/tags/v}"
          PYPROJECT_VERSION=$(grep '^version = ' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

          if [ "$TAG_VERSION" != "$PYPROJECT_VERSION" ]; then
            echo "::error::Tag version ($TAG_VERSION) does not match pyproject.toml ($PYPROJECT_VERSION)"
            exit 1
          fi
          echo "Version $TAG_VERSION validated"

  tests:
    needs: validate-version
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
      - name: Run BDD tests
        run: uv run behave

  build-push:
    needs: tests
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Log in to Container registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract metadata (tags, labels) for Docker
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

  github-release:
    needs: build-push
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))" && echo "YAML valid"
```

- [ ] **Step 3: Verify act parses the workflow**

```bash
HOME=/tmp/act-home act --list -W .github/workflows/release.yml 2>&1 | head -20
```

Expected: lists four jobs — validate-version, tests, build-push, github-release — with correct `needs` dependencies.

- [ ] **Step 4: Stage and commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci: add release workflow for Docker image to ghcr.io"
```

---

### Task 2: Release skill

**Files:**
- Create: `.agents/skills/release/SKILL.md`

**Interfaces:**
- Consumes: none (independent of Task 1)
- Produces: `.agents/skills/release/SKILL.md` — AI agent instructions for the release process

- [ ] **Step 1: Create the skill file**

```bash
mkdir -p .agents/skills/release
```

```markdown
---
name: release
description: Tag-triggered release pipeline for spencer-bot. Bumps version in pyproject.toml, pushes tag, and the release.yml workflow builds + pushes the Docker image to ghcr.io. Use when the user wants to create a new release.
---

# Release Workflow for spencer-bot

Releases are tag-triggered. Push a semver tag (`vX.Y.Z`) and the pipeline builds the Docker image, pushes it to `ghcr.io/<owner>/spencer-bot`, and creates a GitHub Release.

## Release Process

### 1. Determine the new version

Use [Semantic Versioning](https://semver.org/):

- **Major (X.0.0):** breaking changes to the bot's behavior or API
- **Minor (0.Y.0):** new features, backward-compatible
- **Patch (0.0.Z):** bug fixes, no new behavior

### 2. Update pyproject.toml

Edit the `version` field in `pyproject.toml`:

```toml
[project]
version = "1.2.3"
```

### 3. Commit the version bump

```bash
git add pyproject.toml
git commit -m "chore: bump version to 1.2.3"
```

### 4. Create and push the tag

The tag MUST match the version exactly (with `v` prefix):

```bash
git tag v1.2.3
git push origin main
git push origin v1.2.3
```

### 5. What happens automatically

The `release.yml` workflow runs on the tag push:

1. **validate-version** — confirms the tag matches `pyproject.toml` version
2. **tests** — runs `pytest` + `behave` (full test suite)
3. **build-push** — builds Docker image, pushes to `ghcr.io/<owner>/spencer-bot` with tags:
   - `1.2.3` (full version)
   - `1.2` (minor)
   - `latest` (moving tag for latest stable)
4. **github-release** — creates a GitHub Release with auto-generated release notes

### Important notes

- **Pre-release versions** (`v1.2.3-beta.1`, `v1.2.3-rc.1`) work but do NOT get `latest` or `major.minor` Docker tags — only the full version tag
- **Version 0.x.y** follows semver 0.x rules: `0.1.0` → tags `0.1.0`, `0.1`, `latest`
- **Mismatched tag/version** — the `validate-version` job fails fast if the tag doesn't match `pyproject.toml`
- **CI must be green first** — the `tests` job runs the full suite; if it fails, the image is never built
- **No rollback built-in** — to roll back, re-tag an earlier commit and push
```

- [ ] **Step 2: Verify the skill file is valid markdown**

```bash
python3 -c "
from pathlib import Path
content = Path('.agents/skills/release/SKILL.md').read_text()
assert content.startswith('---')
assert 'name: release' in content
assert 'description:' in content
print('Skill file valid')
"
```

- [ ] **Step 3: Stage and commit**

```bash
git add .agents/skills/release/SKILL.md
git commit -m "docs: add release skill for spencer-bot"
```
