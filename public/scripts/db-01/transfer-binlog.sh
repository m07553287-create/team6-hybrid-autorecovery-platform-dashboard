#!/usr/bin/env bash
# 원본: db-01 /opt/minwon-backup/transfer-binlog.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -Eeuo pipefail
SRC=/var/backups/mysql/binlog/
DEST=rocky@10.200.0.4:/var/backups/minwon/incoming/binlog/
KEY=/home/ubuntu/.ssh/id_ed25519_minwon_backup
exec 9>/run/lock/minwon-binlog-transfer.lock
flock -n 9 || exit 1
rsync -av --ignore-existing --delay-updates --timeout=20 -e "ssh -i $KEY -o BatchMode=yes -o ConnectTimeout=5" "$SRC" "$DEST"
echo "AWS Binlog 전송 완료"
