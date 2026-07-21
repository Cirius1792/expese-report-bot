# README Branding Design

**Date:** 2026-07-21
**Status:** Approved

## Goal

Present the project as **(ex)SpenserBot** in the README and display its logo prominently without changing technical identifiers.

## Scope

- Move the temporary root-level `logo.png` to `docs/assets/logo.png`.
- Add a centered README header containing the logo at approximately 240 pixels wide.
- Change the README title from `Expense Report Bot` to `(ex)SpenserBot`.
- Start the opening description with `(ex)SpenserBot is a Telegram bot` while preserving the existing product description.

## Non-goals

- Do not rename the Python package, project metadata, CLI commands, repository directory examples, Docker resources, or other technical identifiers.
- Do not alter unrelated tracked or untracked files.
- Do not introduce new dependencies.

## Rendering

The README will use GitHub-compatible HTML for the centered image and heading because standard Markdown does not provide reliable image sizing. The image source will be the repository-relative path `docs/assets/logo.png` and include descriptive alternative text.

## Verification

- Confirm `docs/assets/logo.png` exists and the root-level `logo.png` no longer exists.
- Confirm the README references the moved asset with a 240-pixel width and descriptive alternative text.
- Confirm the visible project title and opening description use `(ex)SpenserBot`.
- Run the repository formatting, linting, type-checking, and full pytest suite required by `AGENTS.md`.
