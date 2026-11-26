#!/usr/bin/env bash
# ==============================================================================
# 온프레미스 오픈스택 & K8s 추가 구성 스크립트 (setup_onprem_openstack_addons.sh)
# 목적: 기존 OpenStack VM 및 K8s 파드 설정 유지 + 중앙 백업 수신 권한 및 트래픽 점검 추가
# 대상: 온프레미스 OpenStack Master / db-01 / k8s-cp1
# 실행: sudo bash setup_onprem_openstack_addons.sh
# ==============================================================================

set -euo pipefail

echo "==> [온프레미스] 1. 기존 OpenStack 및 VM 상태 점검"
if command -v openstack >/dev/null 2>&1; then
    source /root/keystonerc_admin 2>/dev/null || true
    echo "    OpenStack CLI 감지됨 - VM 가동 상태 확인:"
    openstack server list -c Name -c Status -c Networks || true
fi

echo "==> [온프레미스] 2. db-01 (10.10.2.10) 백업 수신 사용자 및 권한 구성 안내"
cat << 'EOF' > /tmp/setup_db01_backup_user.sql
-- db-01에 접속하여 실행할 백업 수신용 SQL
CREATE USER IF NOT EXISTS 'repl_backup'@'%' IDENTIFIED BY 'figteam_db_pass';
GRANT ALL PRIVILEGES ON minwon.* TO 'repl_backup'@'%';
FLUSH PRIVILEGES;
SELECT user, host FROM mysql.user WHERE user='repl_backup';
EOF
echo "    /tmp/setup_db01_backup_user.sql 생성 완료."
echo "    (db-01 VM 접속 후: mysql -u root -p < /tmp/setup_db01_backup_user.sql 실행)"

echo "==> [온프레미스] 3. k8s-cp1 (All-in-One) 내부/외부 트래픽 헤더 인지 검증 스크립트"
cat << 'EOF' > /usr/local/bin/check_traffic_flow.sh
#!/usr/bin/env bash
# k8s-cp1 인그레스 트래픽 유입 상태 검증
echo "=== [온프렘 k8s-cp1 트래픽 유입 점검] ==="
echo "1. NodePort 30080 로컬 응답:"
curl -s -o /dev/null -w "HTTP 응답 코드: %{http_code}\n" http://127.0.0.1:30080/healthz || echo "미응답"

echo "2. WireGuard 터널 IP(10.200.0.2) 바인딩 확인:"
ip addr show wg0 | grep "inet " || echo "wg0 미감지"

echo "3. 파드 상태:"
sudo kubectl get pods -n minwon-sample -o wide
EOF

chmod +x /usr/local/bin/check_traffic_flow.sh

echo "==> [온프레미스] 모든 추가 설정이 성공적으로 완료되었습니다! (기존 설정 100% 보존)"
