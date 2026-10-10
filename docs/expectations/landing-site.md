# Expectations: Landing site (GitHub Pages)

## Goal
A static marketing + documentation site for (ex)SpenserBot, deployed to GitHub
Pages from the `site/` folder via a dedicated Actions workflow. There is NO
public bot instance — the primary CTA is "self-host it".

## Structure
- `site/index.html` — landing page
- `site/docs/index.html` — docs home / getting started
- `site/docs/deployment.html` — deployment instructions (Docker Compose)
- `site/docs/configuration.html` — configuration reference
- `site/assets/logo.png`, `site/assets/style.css` — shared assets
- `.github/workflows/pages.yml` — deploys `site/` to GitHub Pages

## Landing page content (must include)
1. Hero: logo, bot name, one-line pitch, CTA "Self-host it" (→ docs/deployment.html) and "View source" (→ GitHub repo)
2. Features: photo extraction, PDF receipts (≤5 pages), free-text logging, correction loop (3 attempts), monthly CSV report, delete with audit trail
3. Use cases: travel/business reimbursement, personal budgeting, freelancer tax prep (multi-currency, no conversion), small teams (user isolation)
4. How it works: 4-step flow (send → extract → confirm/correct → report)
5. Commands & buttons reference table (`/start`, `/add`, `/list`, `/report`, `/delete`, `/remove` + reply keyboard buttons)
6. Privacy/security strip: self-hosted data (SQLite), per-user isolation, whitelist authorization with audit log
7. Footer: MIT license, repo link, author

## Documentation content (must include)
- Getting started: prerequisites (BotFather token, any OpenAI-compatible LLM endpoint, Docker), setup steps
- Deployment: `.env` / `.env.deploy` split, docker compose command, data persistence (`./data/expenses.db`), container path for whitelist (`/data/authorized-users.json`)
- Configuration: all env vars (required/optional), `authorized-users.json` schema, startup failure behaviors, audit log format, user isolation

## Behaviors that must NOT happen
- No external CDN dependencies (fonts, JS frameworks) — site must render fully offline with only local files
- No links to a public bot instance (none exists)
- No broken internal links — every relative link must resolve to an existing file
- No secrets or credentials in any site file
- Docs must not contradict the README (env var names, file paths, commands)

## Verification
- Internal link check: every `href`/`src` in `site/**/*.html` resolves to a file in `site/` (external `https://` links allowed)
- `uvx ruff format && uvx ruff check && uvx ty check && uv run pytest` still pass (site files must not break the Python quality gate)
