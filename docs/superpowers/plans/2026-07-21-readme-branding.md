# README Branding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Brand the README as (ex)SpenserBot and display the repository logo.

**Architecture:** This is a documentation-only change. The image moves into the documentation asset directory and the README uses GitHub-compatible HTML to control its presentation.

**Tech Stack:** Markdown, HTML, PNG, Git

## Global Constraints

- Keep all technical package, CLI, Docker, and directory identifiers unchanged.
- Do not add dependencies or alter unrelated files.
- Render the logo from `docs/assets/logo.png` at 240 pixels wide with descriptive alternative text.

---

### Task 1: Brand the README

**Files:**
- Create: `docs/expectations/readme-branding.md`
- Move: `logo.png` to `docs/assets/logo.png`
- Modify: `README.md:1-3`

**Interfaces:**
- Consumes: root-level `logo.png`
- Produces: README-relative image reference `docs/assets/logo.png`

- [ ] **Step 1: Record expectations**

Create `docs/expectations/readme-branding.md` stating that the logo is stored under documentation assets, the README renders it at 240 pixels wide, and visible branding says `(ex)SpenserBot`, while technical identifiers remain unchanged.

- [ ] **Step 2: Move the image and update the README**

Move `logo.png` to `docs/assets/logo.png`. Replace the opening README heading and description with a centered HTML header containing:

```html
<p align="center">
  <img src="docs/assets/logo.png" alt="(ex)SpenserBot logo" width="240">
</p>

<h1 align="center">(ex)SpenserBot</h1>
```

Start the following paragraph with `(ex)SpenserBot is a Telegram bot`.

- [ ] **Step 3: Verify rendered-source requirements**

Run a script that asserts the destination image exists, the root image does not, the README contains the exact image source, width, alternative text, heading, and opening brand name, and technical references remain unchanged.

- [ ] **Step 4: Run the repository quality gate**

Run:

```bash
uvx ruff format
uvx ruff check
uvx ty check
uv run pytest
```

Expected: all commands exit successfully.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/assets/logo.png docs/expectations/readme-branding.md docs/superpowers/plans/2026-07-21-readme-branding.md
git commit -m "docs: brand README as (ex)SpenserBot"
```
