#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/promote-mysql.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
# No unattended promotion until an independently verified fencing provider is integrated.
echo 'BLOCKED: AWS promotion disabled until on-prem fencing verification is integrated.' >&2
exit 1
