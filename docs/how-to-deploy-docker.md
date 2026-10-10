# Docker Deployment Guide

The Docker Compose setup uses **two separate env files** for different purposes to manage environment variables and host-level file ownership correctly.

| File | Purpose | Used by |
|------|---------|---------|
| `.env` | Bot runtime environment variables (`TELEGRAM_BOT_TOKEN`, `LLM_*`, `AUTHORIZED_USERS_CONFIG_PATH` etc.) | `docker-compose.yml` `env_file:` directive — injected into the running container |
| `.env.deploy` | Compose file interpolation (`${UID}`, `${GID}`) | `--env-file .env.deploy` flag — resolved at `docker compose up` time, **not** passed to the container |

### Deployment Steps

```bash
# 1. Copy runtime env file (for container environment)
cp .env.example .env
# Edit .env with your real Telegram token, LLM credentials, and authorization config

# 2. Copy Compose interpolation file (for host file ownership)
cp .env.deploy.example .env.deploy
# Edit .env.deploy UID/GID if your host user is not 1000:1000

# 3. Start with both files — one for interpolation, one for the container
# Compose automatically picks up env_file: .env defined in docker-compose.yml
docker compose --env-file .env.deploy up -d
```

### Database Schema Migrations

The container owns the schema via **Liquibase** (ADR 0013). On every start,
`docker-entrypoint.sh` runs `liquibase update` against `$EXPENSE_DB_PATH`
**before** launching the bot:

- On a fresh deploy the changelog creates the `expenses` table plus the
  `databasechangelog` / `databasechangeloglock` tracking tables.
- On an existing database the changelog is a no-op — already-applied
  changesets are skipped — so restarts are safe and never touch your data.
- If the migration fails, the entrypoint exits non-zero and **the bot does not
  start**. Check the container logs (`docker compose logs`).
- The SQLite JDBC driver ships inside the Liquibase `4.33.0` image, so no
  driver files or `lib/` directory are needed.

To change the schema, append a **new** changeset to
`db/changelog/db.changelog.xml`; never edit an applied changeset.

### Container Behavior

- **User/Permissions**: The container runs as the `UID:GID` specified in `.env.deploy` so the bind-mounted database is owned by the host user.
- **Persistence**: It persists the SQLite database to `./data/expenses.db` on the host.
- **Authorization Configuration**: It reads `AUTHORIZED_USERS_CONFIG_PATH` from `.env` at runtime. 
  - **Note:** In `.env`, you must set `AUTHORIZED_USERS_CONFIG_PATH=/data/authorized-users.json` and place the whitelist file in `./data/` on the host. (The default from `.env.example` is a local path — Docker needs the container path.)
- **Audit Logging**: Optionally set `UNAUTHORIZED_LOG_PATH=/data/unauthorized.log` in `.env` for a dedicated audit log inside the same persisted volume.
- **Lifecycle**: It uses `restart: unless-stopped` to ensure high availability.

