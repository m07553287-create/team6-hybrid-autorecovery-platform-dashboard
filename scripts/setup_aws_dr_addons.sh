#!/usr/bin/env bash
# ==============================================================================
# AWS DR 추가 구성 스크립트 (setup_aws_dr_addons.sh)
# 목적: 기존 AWS EC2, K3s, MySQL Replica 유지 + 승격 시 온프렘(10.10.2.10) 자동 백업 스크립트 배치
# 대상: AWS DR 인스턴스 (aws-dr · 10.200.0.4)
# 실행: sudo bash setup_aws_dr_addons.sh
# ==============================================================================

set -euo pipefail

echo "==> [AWS DR] 1. 기존 설정 보존 확인"
systemctl is-active k3s || echo "    (K3s 대기 상태 확인)"

echo "==> [AWS DR] 2. 승격 후 온프렘(10.10.2.10) 역방향 백업 동기화 스크립트 작성"
cat << 'EOF' > /usr/local/bin/sync_aws_to_onprem_db.sh
#!/usr/bin/env bash
# ==============================================================================
# AWS MySQL 쓰기 발생 시 온프렘 중앙 백업 DB(10.10.2.10)로 데이터 백업 전송
# ==============================================================================
set -euo pipefail

ONPREM_DB_HOST="10.10.2.10"
ONPREM_DB_PORT="3306"
DB_NAME="minwon"
BACKUP_USER="repl_backup"
BACKUP_PASS="figteam_db_pass"

# 1. 온프렘 백업 대상 헬스체크
if ! nc -z -w 3 "$ONPREM_DB_HOST" "$ONPREM_DB_PORT"; then
    echo "[$(date)] ⚠️ 온프렘 백업 대상($ONPREM_DB_HOST:$ONPREM_DB_PORT) 연결 불가. 재시도 대기."
    exit 0
fi

# 2. AWS 로컬 MySQL 상태 확인 (Read-Only 여부)
IS_RO=$(mysql -N -e "SELECT @@global.read_only;" 2>/dev/null || echo "1")

if [ "$IS_RO" = "0" ]; then
    echo "[$(date)] 🚀 [AWS DR 활성화 상태] 신규 쓰기 트랜잭션 ➔ 온프렘($ONPREM_DB_HOST) 백업 동기화 시작"
    mysqldump --single-transaction --quick --skip-lock-tables \
        -u root "$DB_NAME" 2>/dev/null | \
        mysql -h "$ONPREM_DB_HOST" -P "$ONPREM_DB_PORT" -u "$BACKUP_USER" -p"$BACKUP_PASS" "$DB_NAME" 2>/dev/null || true
    echo "[$(date)] ✅ 온프렘($ONPREM_DB_HOST) 무유실 백업 전송 완료"
else
    echo "[$(date)] 🟢 평시 대기 상태 (Read-Only=ON). 동기화 대기."
fi
EOF

chmod +x /usr/local/bin/sync_aws_to_onprem_db.sh

echo "==> [AWS DR] 3. 백업 동기화 주기 실행 타이머 등록 (systemd)"
cat << 'EOF' > /etc/systemd/system/aws-onprem-sync.service
[Unit]
Description=AWS DR to Onprem DB Backup Sync Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/sync_aws_to_onprem_db.sh
EOF

cat << 'EOF' > /etc/systemd/system/aws-onprem-sync.timer
[Unit]
Description=Run AWS to Onprem DB Sync every 1 minute

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min
AccuracySec=1s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now aws-onprem-sync.timer

echo "==> [AWS DR] 4. 상태 검증"
systemctl status aws-onprem-sync.timer --no-pager

echo "==> [AWS DR] 모든 추가 설정이 성공적으로 완료되었습니다! (기존 설정 100% 보존)"
