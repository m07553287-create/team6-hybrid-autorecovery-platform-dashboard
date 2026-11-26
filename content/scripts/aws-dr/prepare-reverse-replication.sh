#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/prepare-reverse-replication.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
echo "=== Failback 동기화 준비 ==="
bash /opt/minwon-dr/failback-precheck.sh
echo "AWS 기준 온프레미스 재동기화 및 역방향 복제 설정 필요"
echo "역방향 복제 자동 실행은 아직 미구현"
exit 2
