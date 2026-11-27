#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/mysql-reverse-tunnel.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
exec /usr/local/bin/k3s kubectl port-forward --address 10.200.0.4 -n minwon-dr svc/minwon-mysql 13306:3306
