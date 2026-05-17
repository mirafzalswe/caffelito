#!/usr/bin/env bash
# Daily Postgres backup with 14-day rotation. Installed to /usr/local/sbin/
# by install.sh and triggered by /etc/cron.d/coffee-pg-backup at 03:30 UTC.
# Runs as the `postgres` system user.
set -euo pipefail
cd /tmp

BACKUP_DIR="/var/backups/coffee"
KEEP_DAYS=14
DB="coffee_loyalty"
TS="$(date +%Y-%m-%d_%H%M)"
OUT="$BACKUP_DIR/${DB}_${TS}.dump"

pg_dump -F c -f "$OUT" "$DB"
chmod 600 "$OUT"

find "$BACKUP_DIR" -name "${DB}_*.dump" -type f -mtime +${KEEP_DAYS} -delete
ln -sf "$OUT" "$BACKUP_DIR/${DB}_latest.dump"

SIZE_MB=$(du -m "$OUT" | cut -f1)
logger -t coffee-pg-backup "ok dump=$OUT size=${SIZE_MB}MB"
