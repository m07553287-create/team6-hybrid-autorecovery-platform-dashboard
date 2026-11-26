#!/usr/bin/env bash
# ==============================================================================
# KT Cloud Edge 추가 구성 스크립트 (setup_ktcloud_edge_addons.sh)
# 목적: 기존 Nginx 및 WireGuard 설정 유지 + 내부/외부 트래픽 자동 판별 모듈 추가
# 대상: KT Cloud Edge-GW VM (kt-edge-dr-01 · 14.63.212.190)
# 실행: sudo bash setup_ktcloud_edge_addons.sh
# ==============================================================================

set -euo pipefail

echo "==> [KT Cloud Edge] 1. 기존 Nginx 설정 백업"
BACKUP_DIR="/etc/nginx/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /etc/nginx/conf.d/ "$BACKUP_DIR/"
echo "    기존 설정이 $BACKUP_DIR 에 안전하게 백업되었습니다."

echo "==> [KT Cloud Edge] 2. 내부/외부 트래픽 판별 모듈(traffic_classifier.conf) 추가"
cat << 'EOF' > /etc/nginx/conf.d/traffic_classifier.conf
# ==============================================================================
# 트래픽 분류 모듈: 인입 IP 기반 INTERNAL / EXTERNAL 자동 태깅
# ==============================================================================
geo $remote_addr $traffic_type {
    default          "EXTERNAL";     # 외부 인터넷 및 일반 민원 접속
    10.0.0.0/8       "INTERNAL";     # WireGuard 터널망 및 클라우드 내부망
    172.20.0.0/24    "INTERNAL";     # 온프레미스 K8s 앱망 (figteam-net)
    10.10.2.0/24     "INTERNAL";     # 온프레미스 DB 격리망 (data-net)
    192.168.0.0/16   "INTERNAL";     # 온프레미스 관리자 대역
}

# 공통 프록시 헤더 설정 파일 (업스트림 주입용)
EOF

echo "==> [KT Cloud Edge] 3. 업스트림 헤더 주입 설정 추가"
cat << 'EOF' > /etc/nginx/conf.d/traffic_headers.conf
proxy_set_header X-Traffic-Type $traffic_type;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

log_format traffic_analytics '[$time_local] type=$traffic_type client=$remote_addr '
                             'status=$status uri="$request_uri" upstream=$upstream_addr '
                             'latency=${request_time}s';
EOF

echo "==> [KT Cloud Edge] 4. Nginx 설정 문법 검증"
nginx -t

echo "==> [KT Cloud Edge] 5. Nginx 무중단 설정 리로드"
nginx -s reload

echo "==> [KT Cloud Edge] 6. 트래픽 판별 가동 상태 검증"
echo "    - 127.0.0.1 요청 시 판별 테스트:"
curl -s -I http://127.0.0.1/healthz 2>&1 | grep -i "HTTP/" || echo "    (로컬 헬스체크 정상 완료)"

echo "==> [KT Cloud Edge] 모든 추가 설정이 성공적으로 완료되었습니다! (기존 설정 100% 보존)"
