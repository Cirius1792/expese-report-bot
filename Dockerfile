# ADR 0013: Liquibase owns the database schema. The image embeds the Liquibase
# CLI (official 4.33.0 image base), which bundles the SQLite JDBC driver — so
# no driver jars are committed or fetched and no --classpath is needed.
# (Liquibase 5.x dropped bundled drivers and relies on the unreliable `lpm`;
# see ADR 0013.) The bot is installed on top with uv.
FROM liquibase/liquibase:4.33.0

# The official image runs as the unprivileged `liquibase` user. Switch to root
# for the build steps below; a non-root `USER` is set again at the end.
USER root

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install the managed CPython distribution into a world-readable location.
# uv defaults to ~/.local/share/uv/python (/root/... during the build), but
# /root is mode 0700, so the venv's `python` symlink would be unreachable for
# the non-root runtime user ("Permission denied" when launching the bot).
ENV UV_PYTHON_INSTALL_DIR=/opt/python

WORKDIR /app

# First layer: dependencies only (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --no-install-project --frozen

# Second layer: application source
COPY src/ ./src/
COPY db/ ./db/
COPY docker-entrypoint.sh ./docker-entrypoint.sh

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen

# Make /app, the Liquibase distribution, and the managed Python world-readable
# so any UID can run them
RUN chmod -R a+rX /app /liquibase /opt/python

# Create non-root user with home directory (UID/GID overridable at runtime)
RUN groupadd -r botuser && useradd -r -m -g botuser botuser

# Shared cache directory (writable by any UID — used by dspy and others)
RUN mkdir -p /tmp/cache && chmod 1777 /tmp/cache

# Data directory for SQLite database (bind-mounted at runtime)
RUN mkdir -p /data && chmod 1777 /data
VOLUME /data

ENV EXPENSE_DB_PATH=/data/expenses.db
ENV HOME=/tmp
ENV XDG_CACHE_HOME=/tmp/cache
# Unbuffered Python: ensure logs are flushed immediately to stdout/stderr
# so Docker log collector captures them in real time
ENV PYTHONUNBUFFERED=1

USER botuser

# Entrypoint: run Liquibase migrations, then exec the bot (ADR 0013)
ENTRYPOINT ["/app/docker-entrypoint.sh"]
