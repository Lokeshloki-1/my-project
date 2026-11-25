#!/bin/sh
# Restore the Hazpo database from a backup made by backup.sh.
#   ./scripts/restore.sh backups/hazpo-2026-11-25_0200.dump
# WARNING: this REPLACES all current data with the backup's data.
set -eu
cd "$(dirname "$0")/.."
. ./.env.prod
DUMP="${1:?Usage: ./scripts/restore.sh backups/hazpo-YYYY-MM-DD_HHMM.dump}"
[ -f "$DUMP" ] || { echo "No such file: $DUMP"; exit 1; }
printf 'This replaces ALL current data in "%s" with %s. Type RESTORE to continue: ' "$POSTGRES_DB" "$DUMP"
read -r answer
[ "$answer" = "RESTORE" ] || { echo "Cancelled."; exit 1; }
C="docker compose -f docker-compose.prod.yml --env-file .env.prod"
$C stop backend
$C exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$DUMP"
$C start backend
echo "Restored from $DUMP."
