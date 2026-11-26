#!/bin/bash
# 원본: db-01 /opt/minwon-backup/transfer-full.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
rsync -av --chmod=F600 --ignore-existing --delay-updates --timeout=20 -e "ssh -i /home/ubuntu/.ssh/id_ed25519_minwon_backup -o BatchMode=yes -o ConnectTimeout=5" /var/backups/mysql/minwon-20*.sql.gz rocky@10.200.0.4:/var/backups/minwon/incoming/full/
ssh -i /home/ubuntu/.ssh/id_ed25519_minwon_backup -o BatchMode=yes -o ConnectTimeout=5 rocky@10.200.0.4 "bash /home/rocky/minwon-backup/upload-full.sh"
