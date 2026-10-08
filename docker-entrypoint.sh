#!/bin/sh
set -eu

# ADR 0013: Liquibase owns the schema. Migrate before the bot starts;
# a failed migration exits non-zero and the bot never launches.
# Liquibase 4.x bundles the SQLite JDBC driver, so no --classpath is needed.
if [ -z "${EXPENSE_DB_PATH:-}" ]; then
  echo "docker-entrypoint: EXPENSE_DB_PATH must be set and non-empty" >&2
  exit 1
fi

# Run Liquibase in a subshell so the exec'd bot keeps the image WORKDIR (/app):
# --changelog-file must stay relative to /app/db (absolute changelog paths are
# unreliable, ADR 0013), but a bare `cd /app/db` would make relative input paths
# (AUTHORIZED_USERS_CONFIG_PATH, UNAUTHORIZED_LOG_PATH) resolve in the wrong
# directory. --validate-xml-changelog-files=false avoids a remote XSD fetch
# (offline-safe).
(
  cd /app/db
  liquibase \
    --validate-xml-changelog-files=false update \
    --url="jdbc:sqlite:${EXPENSE_DB_PATH}" \
    --changelog-file=changelog/db.changelog.xml
)

# This entrypoint is the container's single migrator. Signal the bot so it does
# not launch a second, redundant Liquibase JVM; `main()` still migrates when the
# process is started outside the container.
export EXPENSE_SCHEMA_MIGRATED=1
exec /app/.venv/bin/expense-bot
