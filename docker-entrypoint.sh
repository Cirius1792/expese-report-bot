#!/bin/sh
set -e

# ADR 0013: Liquibase owns the schema. Migrate before the bot starts;
# a failed migration exits non-zero and the bot never launches.
# Liquibase 4.x bundles the SQLite JDBC driver, so no --classpath is needed.
# Liquibase resolves --changelog-file against the CWD (no absolute paths), and
# --validate-xml-changelog-files=false avoids a remote XSD fetch (offline-safe).
cd /app/db
liquibase \
  --validate-xml-changelog-files=false update \
  --url="jdbc:sqlite:${EXPENSE_DB_PATH}" \
  --changelog-file=changelog/db.changelog.xml

exec /app/.venv/bin/expense-bot
