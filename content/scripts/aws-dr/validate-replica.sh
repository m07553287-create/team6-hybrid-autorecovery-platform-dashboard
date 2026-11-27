#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/validate-replica.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
STATUS=$(sudo /usr/local/bin/k3s kubectl exec -n minwon-dr minwon-mysql-0 -- sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e "SHOW REPLICA STATUS\G"')
check() {
  grep -Eq "^[[:space:]]*$1:[[:space:]]*$2[[:space:]]*$" <<< "$STATUS" || { echo "FAIL: $1"; exit 1; }
}
check Replica_IO_Running Yes
check Replica_SQL_Running Yes
check Last_IO_Errno 0
check Last_SQL_Errno 0
check Seconds_Behind_Source 0
echo "PASS: Replica 복제 상태 정상"
echo "주의: Primary 격리 및 최종 GTID 검증은 별도 필요"
