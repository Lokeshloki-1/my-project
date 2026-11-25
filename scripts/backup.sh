#!/bin/sh
# Back up the Hazpo database to backups/hazpo-YYYY-MM-DD_HHMM.dump and keep the last 14 days.
# Run from the project folder on the server:   ./scripts/backup.sh
# Daily at 2am (crontab -e):   0 2 * * * cd /path/to/my-project && ./scripts/backup.sh >> backups/backup.log 2>&1
# Copy the backups folder somewhere else too (another server, cloud storage) — a backup on the same disk is lost with the disk.
set -eu
cd "$(dirname "$0")/.."
. ./.env.prod
mkdir -p backups
FILE="backups/hazpo-$(date +%Y-%m-%d_%H%M).dump"
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom > "$FILE.tmp"
mv "$FILE.tmp" "$FILE"
echo "$(date '+%F %T') saved $FILE ($(du -h "$FILE" | cut -f1))"
find backups -name 'hazpo-*.dump' -mtime +14 -delete
