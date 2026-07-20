# Docker Release Workflow + Release Skill Design

**Date:** 2026-07-20
**Status:** approved

## Goal

Add a GitHub Actions release workflow that builds and pushes a Docker image to GitHub Container Registry (ghcr.io) when a version tag is pushed, plus an agent skill documenting the release process.

## Scope

- **In:** tag-triggered release workflow (validate → test → build-push → GitHub Release), release skill for AI agents
- **Out:** automated version bumping, conventional commits enforcement, PyPI publishing, Docker Hub, multi-arch builds

## Image naming

- Registry: `ghcr.io`
- Image: `ghcr.io/<owner>/spencer-bot` (uses `${{ github.repository_owner }}` dynamically)

## Triggers

```yaml
on:
  push:
    tags:
      - 'v*'
```

Only semver-formatted tags (`v1.2.3`, `v0.1.0`, `v1.2.3-beta.1`). Non-semver tags (`vfoo`) are ignored by `docker/metadata-action` semver type.

## Architecture

```
tag push (v1.2.3)
     │
     ▼
┌─────────────────────┐
│ validate-version     │  → tag == pyproject.toml version?
└──────────┬──────────┘
           │ (if match)
           ▼
┌─────────────────────┐
│ tests                │  → uv sync --dev --frozen → pytest → behave
└──────────┬──────────┘
           │ (if pass)
           ▼
┌─────────────────────┐
│ build-push           │  → docker build + push to ghcr.io
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ github-release       │  → create GitHub Release with auto notes
└─────────────────────┘
```

### Job: validate-version

Strips `v` prefix from `GITHUB_REF`, compares against `pyproject.toml` `version` field. Fails if mismatch — prevents pushing an image tagged `1.2.3` when the code says `1.2.2`.

### Job: tests

Runs the full test suite: `uv sync --dev --frozen`, `uv run pytest`, `uv run behave`. Needs `validate-version` to pass. Ensures the tagged code is green before any image leaves the pipeline.

### Job: build-push

Uses `docker/login-action` (ghcr.io, `GITHUB_TOKEN`) + `docker/metadata-action` (semver tags) + `docker/build-push-action`.

Needs `packages: write` and `contents: read`.

Docker tags produced by `docker/metadata-action` with semver pattern:

```yaml
tags: |
  type=semver,pattern={{version}}
  type=semver,pattern={{major}}.{{minor}}
```

| Git tag | Docker tags |
|---|---|
| `v1.2.3` | `ghcr.io/<owner>/spencer-bot:1.2.3`, `:1.2`, `:latest` |
| `v0.1.0` | `ghcr.io/<owner>/spencer-bot:0.1.0`, `:0.1`, `:latest` |
| `v1.2.3-beta.1` | `ghcr.io/<owner>/spencer-bot:1.2.3-beta.1` (no `latest`, no `1.2`) |

### Job: github-release

Uses `softprops/action-gh-release@v2` with `generate_release_notes: true` (GitHub auto-generates from merged PRs since last release).

Needs `contents: write`.

If `build-push` failed, this job is skipped — no release without a built image.

## Release skill

Location: `.agents/skills/release/SKILL.md`

Documents the manual release process for an AI agent:

1. Determine the new version (semver judgment)
2. Update `version` in `pyproject.toml`
3. Commit: `chore: bump version to X.Y.Z`
4. Create tag: `git tag vX.Y.Z`
5. Push: `git push origin main && git push origin vX.Y.Z`

Warns about:
- Tag must match `pyproject.toml` exactly (the pipeline validates this)
- Pre-release versions (beta, rc) won't get `latest` Docker tag
- The CI workflow runs on every push and must be green before tagging

## Files

- Create: `.github/workflows/release.yml`
- Create: `.agents/skills/release/SKILL.md`

## Design decisions

- **Tag-triggered, not push-to-main** — releases are intentional, explicit, and the tag IS the version
- **Manual versioning** — developer chooses patch/minor/major; no conventional commits automation needed for a single-contributor bot
- **`validate-version` first** — catches version mismatches in 5 seconds instead of after a 2-minute test+push cycle
- **Tests run on every release** — the CI workflow covers pushes to main but not tags; the release workflow includes tests to guarantee green-on-release even if CI was skipped
- **`softprops/action-gh-release` over GitHub's native `gh release`** — works natively in Actions, handles asset uploads if needed later
- **`generate_release_notes: true`** — GitHub auto-generates notes from merged PRs, good enough for a bot, no changelog maintenance overhead
- **Skill lives in `.agents/skills/release/`** — follows the project's existing skill location pattern (`.agents/skills/github-actions-templates/`, `.agents/skills/github-workflow-automation/`, `.agents/skills/python-best-practices/`, `.agents/skills/python-testing-patterns/`, `.agents/skills/behave-skill/`)

## Out of scope

- Automated version bumping (python-semantic-release, release-please)
- Conventional commits enforcement
- PyPI publishing
- Docker Hub mirroring
- Multi-arch builds (amd64 only for now)
- Image signing / attestation
- `docker-compose.yml` update to reference the ghcr.io image
