#!/usr/bin/env bash
# 원본: db-01 /opt/minwon-backup/backup-binlog.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -Eeuo pipefail
BACKUP_DIR=/var/backups/mysql/binlog
BINLOG_DIR=/var/lib/mysql
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
exec 9>/run/lock/minwon-binlog.lock
flock -n 9 || { echo "ERROR: 이미 실행 중"; exit 1; }
LOGS=$(mysql -NBe "SHOW BINARY LOGS") || { echo "ERROR: Binlog 목록 조회 실패"; exit 1; }
ACTIVE=$(mysql -NBe "SHOW BINARY LOG STATUS") || { echo "ERROR: 활성 Binlog 조회 실패"; exit 1; }
ACTIVE=${ACTIVE%%[[:space:]]*}
[[ -n "$ACTIVE" && -n "$LOGS" ]] || exit 1
while read -r FILE SIZE REST; do
 [[ -n "$FILE" ]] || continue
 [[ "$FILE" == "$ACTIVE" ]] && continue
 SRC="$BINLOG_DIR/$FILE"
 DST="$BACKUP_DIR/$FILE"
 [[ -f "$SRC" ]] || { echo "ERROR: 원본 없음 $FILE"; exit 1; }
 if [[ -f "$DST" ]]; then cmp -s "$SRC" "$DST" || { echo "ERROR: 기존 백업 불일치 $FILE"; exit 1; }; continue; fi
 TMP=$(mktemp "$BACKUP_DIR/.${FILE}.XXXXXX")
 if ! cp "$SRC" "$TMP" || ! cmp -s "$SRC" "$TMP"; then rm -f "$TMP"; echo "ERROR: 복사 실패 $FILE"; exit 1; fi
 chmod 600 "$TMP"
 mv "$TMP" "$DST"
 echo "OK: $FILE 백업 완료"
done <<< "$LOGS"
echo "Binlog 로컬 백업 완료"
