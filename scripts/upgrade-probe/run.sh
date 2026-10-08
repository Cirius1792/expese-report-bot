#!/bin/sh
# End-to-end upgrade probe: seed a database with the latest tagged release's
# real CLI (LLM boundary stubbed), then migrate it with the PR image and verify
# that the legacy rows survive and the schema moves to Liquibase.
#
# Opt-in only — it pulls an old image from ghcr.io, so it is not part of CI.
#
# Usage:
#   docker build -t expense-report-bot:local .
#   scripts/upgrade-probe/run.sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

OLD_IMAGE="${OLD_IMAGE:-ghcr.io/cirius1792/spencer-bot:0.7.0}"
NEW_IMAGE="${NEW_IMAGE:-expense-report-bot:local}"
USER_ID=42

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
DATA="$WORKDIR/data"
mkdir -p "$DATA"
chmod 777 "$DATA"

seed() {
    # seed <amount> <merchant> <date> <category> <text>
    docker run --rm \
        -v "$DATA":/data \
        -v "$SCRIPT_DIR":/stub:ro \
        -e PYTHONPATH=/stub \
        -e LLM_BASE_URL=http://stub -e LLM_API_KEY=stub -e LLM_MODEL=stub \
        -e STUB_AMOUNT="$1" -e STUB_MERCHANT="$2" -e STUB_DATE="$3" -e STUB_CATEGORY="$4" \
        --entrypoint /app/.venv/bin/expense-extract \
        "$OLD_IMAGE" \
        --user-id "$USER_ID" --db /data/expenses.db \
        extract-from-text "$5"
}

echo "== 1/4 seed legacy DB with $OLD_IMAGE (LLM stubbed) =="
seed 12.50 "Legacy Cafe" 2026-01-02 food "lunch 12.50 EUR"
seed 40.00 "Legacy Books" 2026-01-15 books "books 40 EUR"

echo "== 2/4 legacy snapshot =="
BEFORE=$(python3 "$SCRIPT_DIR/inspect_db.py" "$DATA/expenses.db")
echo "$BEFORE"

echo "== 3/4 migrate with $NEW_IMAGE (real entrypoint) =="
# The probe container has no Telegram/LLM credentials, so the bot exits after
# the migration step; that is expected. The migration has already persisted.
if docker run --rm \
    -e TELEGRAM_BOT_TOKEN=0:probe -e EXPENSE_DB_PATH=/data/expenses.db \
    -v "$DATA":/data "$NEW_IMAGE"; then
    echo "bot exited 0"
else
    echo "bot exited non-zero after migrating (expected: no LLM credentials)"
fi

echo "== 4/4 post-migration snapshot + verification =="
AFTER=$(python3 "$SCRIPT_DIR/inspect_db.py" "$DATA/expenses.db")
echo "$AFTER"
python3 "$SCRIPT_DIR/verify.py" "$BEFORE" "$AFTER"

echo "== read back through $NEW_IMAGE repository =="
docker run --rm \
    -v "$DATA":/data -v "$SCRIPT_DIR":/stub:ro \
    --entrypoint /app/.venv/bin/python "$NEW_IMAGE" /stub/read_back.py
