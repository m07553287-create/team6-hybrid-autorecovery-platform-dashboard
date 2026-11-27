#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/check-gtid.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
EXPECTED_GTID="${1:?Usage: check-gtid.sh PRIMARY_GTID}"
[[ "$EXPECTED_GTID" =~ ^[0-9a-fA-F:,-]+$ ]] || { echo 'FAIL: invalid GTID set'; exit 1; }
K=/usr/local/bin/k3s
MYSQL='MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --batch --skip-column-names'
actual="$(sudo "$K" kubectl exec -n minwon-dr minwon-mysql-0 -- sh -c "$MYSQL -e 'SELECT @@GLOBAL.gtid_executed'" | tr -d '\r\n')"
# The replica may contain legitimate AWS-origin GTIDs from previous promotion cycles.
# Requiring literal GTID equality would incorrectly reject those histories.
result="$(sudo "$K" kubectl exec -n minwon-dr minwon-mysql-0 -- sh -c "$MYSQL -e \"SELECT GTID_SUBSET('$EXPECTED_GTID', @@GLOBAL.gtid_executed)\"" | tr -d '\r\n')"
[[ "$result" == 1 ]] || { echo 'FAIL: source final GTID is not fully executed on AWS'; exit 1; }
echo "PASS: source final GTID subset is applied on AWS (actual=$actual)"
echo 'WARNING: GTID coverage alone does not prove primary fencing, no outstanding writes, or application consistency.'
