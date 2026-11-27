#!/usr/bin/env bash
# wiki-01 일일 백업: Redis 스냅샷(RDB) → /var/backups/figteam-wiki, 14일 보관
# BACKUP_REMOTE(예: rocky@10.200.0.4:/var/backups/minwon/incoming/wiki/) 가 있으면 rsync 로 한 부 더 보낸다.
set -euo pipefail
set -a; . /etc/figteam-wiki/env; set +a
export REDISCLI_AUTH="$REDIS_PASSWORD"
DIR=/var/backups/figteam-wiki
F="$DIR/wiki-$(date +%F_%H%M).rdb"
redis-cli --no-auth-warning --rdb "$F.part" >/dev/null
[ -s "$F.part" ]
mv "$F.part" "$F"; chmod 600 "$F"
find "$DIR" -name 'wiki-*.rdb' -mtime +14 -delete
if [ -n "${BACKUP_REMOTE:-}" ]; then rsync -a --timeout=20 "$F" "$BACKUP_REMOTE"; fi
logger -t figteam-wiki-backup "ok $F $(stat -c %s "$F")B"
