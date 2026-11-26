#!/usr/bin/env bash
# 원본: db-01 /opt/minwon-backup/run-backup.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -Eeuo pipefail
exec 9>/run/lock/minwon-binlog-cycle.lock
flock -n 9 || exit 1
mysql -e "FLUSH BINARY LOGS;"
bash /opt/minwon-backup/backup-binlog.sh
bash /opt/minwon-backup/transfer-binlog.sh
ssh -i /home/ubuntu/.ssh/id_ed25519_minwon_backup -o BatchMode=yes -o ConnectTimeout=5 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 rocky@10.200.0.4 "bash /home/rocky/minwon-backup/upload-binlog.sh"
