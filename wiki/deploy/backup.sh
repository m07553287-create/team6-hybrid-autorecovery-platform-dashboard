#!/usr/bin/env bash
# wiki-01 일일 백업: SQLite 온라인 백업 → /var/backups/figteam-wiki, 14일 보관
# BACKUP_REMOTE(예: rocky@10.200.0.4:/var/backups/minwon/incoming/wiki/) 가 있으면 rsync 로 한 부 더 보낸다.
set -euo pipefail
DB=/var/lib/figteam-wiki/wiki.db
DIR=/var/backups/figteam-wiki
F="$DIR/wiki-$(date +%F_%H%M).db"
sqlite3 "$DB" ".backup '$F.part'"
sqlite3 "$F.part" "PRAGMA integrity_check;" | grep -qx ok
mv "$F.part" "$F"; chmod 600 "$F"
find "$DIR" -name 'wiki-*.db' -mtime +14 -delete
if [ -n "${BACKUP_REMOTE:-}" ]; then rsync -a --timeout=20 "$F" "$BACKUP_REMOTE"; fi
logger -t figteam-wiki-backup "ok $F $(stat -c %s "$F")B"
