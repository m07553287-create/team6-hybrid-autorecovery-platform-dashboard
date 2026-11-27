#!/bin/bash
# 원본: db-01 /usr/local/sbin/mysql-backup.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
# db-01 일일 논리 백업 (GTID 포함) — 데이터 볼륨(/var/lib/mysql)과 다른 루트 디스크에 7일 보관
set -euo pipefail
D=/var/backups/mysql; mkdir -p -m 700 $D
F=$D/minwon-$(date +%F_%H%M).sql.gz
mysqldump --single-transaction --set-gtid-purged=ON --triggers --routines --events --databases minwon_db repl_check | gzip > $F.part
mv $F.part $F; chmod 600 $F
find $D -name 'minwon-*.sql.gz' -mtime +7 -delete
logger -t mysql-backup "ok $F $(stat -c %s $F)B"
