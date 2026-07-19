FROM python:3.12-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# First layer: dependencies only (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --frozen

# Second layer: application source
COPY src/ ./src/

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

# Make /app world-readable so any UID can access the venv and source
RUN chmod -R a+rX /app

# Create non-root user with home directory (UID/GID overridable at runtime)
RUN groupadd -r botuser && useradd -r -m -g botuser botuser

# Data directory for SQLite database (bind-mounted at runtime)
RUN mkdir -p /data && chmod 1777 /data
VOLUME /data

ENV EXPENSE_DB_PATH=/data/expenses.db

USER botuser

# Run the pre-installed script directly (no uv sync at runtime)
ENTRYPOINT ["/app/.venv/bin/expense-bot"]
