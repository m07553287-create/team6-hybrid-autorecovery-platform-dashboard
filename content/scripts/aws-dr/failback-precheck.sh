#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/failback-precheck.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
K=/usr/local/bin/k3s
echo "=== AWS DB 상태 ==="
sudo "$K" kubectl exec -n minwon-dr minwon-mysql-0 -- sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -e "SELECT @@read_only, @@super_read_only, @@GLOBAL.gtid_executed;"'
echo "=== 온프레미스 DB 접근 확인 ==="
timeout 5 bash -c "echo >/dev/tcp/10.10.2.10/3306" && echo "MySQL 포트 연결 가능"
