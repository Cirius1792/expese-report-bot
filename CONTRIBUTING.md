# Contributing to (ex)SpenserBot

Thank you for your interest in contributing! This project maintains a very high standard of technical rigor, utilizing **Hexagonal Architecture** and **Expectation-Driven Development (EDD)**. 

To maintain this quality, we follow a strict development lifecycle. Please read this guide thoroughly before submitting your first Pull Request.

---

## 🚀 Getting Started

### Prerequisites
* **Python 3.12+**
* **uv**: Our package manager and tool runner ([Installation](https://docs.astral.sh/uv/getting-started/installation/))

### Local Setup
1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd expense-report-bot
   ```
2. **Install dependencies:**
   ```bash
   uv sync
   ```
3. **Install pre-commit hooks:**
   All commits are scanned for secrets using `gitleaks`.
   ```bash
   uv run pre-commit install
   ```

---

## 🛠 The Development Workflow (EDD)

We use **Expectation-Driven Development (EDD)**. You do not write code until you have defined what success looks like.

### 1. Open an Issue
Before starting any work on a new feature, enhancement, or bug fix, **open an issue** on GitHub. This allows the community to discuss the approach and ensures we are solving the right problem.

### 2. Define Expectations
Create a file in `docs/expectations/<feature-name>.md`. This file must outline:
* **The Happy Path**: The ideal user journey.
* **Edge Cases**: How the system should behave under unusual conditions.
* **Non-Goals**: What this feature specifically will *not* do.

### 3. Test-Driven Development (TDD)
Implement your changes using the **Red-Green-Refactor** loop:
1. **RED**: Write a failing test.
    * Use `pytest` for unit and integration tests (`tests/`).
    * Use `behave` for BDD acceptance tests (matching user stories).
2. **GREEN**: Implement the minimal amount of code necessary to make the test pass.
3. **REFACTOR**: Clean up your code while ensuring all tests remain green.

### 4. Architectural Integrity (Hexagonal Architecture)
We strictly follow **Hexagonal (Ports & Adapters) Architecture**. Your implementation must respect these boundaries:

* **Domain Layer (`src/expense_report/domain/`)**:
    * Must be "Pure": Zero imports from frameworks, I/O libraries, or external APIs.
    * Uses frozen dataclasses for entities and value objects.
    * Contains all core business logic.
* **Ports Layer (`src/expense_report/ports/`)**:
    * Defines the interfaces (Protocols/ABCs) that the domain uses to communicate with the outside world.
* **Adapters Layer (`src/expense_report/adapters/`)**:
    * **Inbound (Driving)**: Entry points like the Telegram bot or CLI.
    * **Outbound (Driven)**: Implementations of ports, such as the SQLite repository or dSPy LLM client.

**Rule of thumb:** Dependencies always point inward toward the Domain. The Domain knows nothing about Telegram, SQLite, or OpenAI.

---

## ✅ Quality Gate & Submission

### Local Verification
Before submitting a PR, you **must** run the following command suite to ensure code quality:

```bash
uvx ruff format && uvx ruff check && uv ty check && uv run pytest && uv run behave
```

*   `ruff`: Ensures consistent formatting and linting.
*   `ty`: Ensures strict type safety.
*   `pytest`: Validates logic and integration.
*   `behave`: Validates business requirements (BDD).

### Pull Request Requirements
Do not push directly to `main`. All changes must be submitted via a Pull Request from a feature branch.

**Your PR description must include "Evidence of Success":**
We do not accept claims like "tests pass" or "it works." You must paste the **actual terminal output** of your successful test runs in the PR description.

Furthermore, you must explicitly map your **Expectations** to your **Evidence**:
* *Expectation 1: ... -> [Paste Pytest/Behave output snippet]*
* *Expectation 2: ... -> [Paste Pytest/Behave output snippet]*

### License
This project is licensed under the MIT License.
