#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/check-replica.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
echo "=== AWS MySQL DR 사전 점검 ==="
sudo /usr/local/bin/k3s kubectl exec -n minwon-dr minwon-mysql-0 -- sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SHOW REPLICA STATUS\G; SHOW GLOBAL VARIABLES WHERE Variable_name IN ('"'"'read_only'"'"','"'"'super_read_only'"'"');"'
echo "=== 점검 완료: DB 변경 없음 ==="
