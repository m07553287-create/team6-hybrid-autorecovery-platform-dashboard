#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/preflight.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: preflight.sh FINAL_SOURCE_GTID' >&2; exit 2; }
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$DIR/validate-replica.sh"
bash "$DIR/check-gtid.sh" "$1"
# Intentionally fail closed until real fencing is integrated.
bash "$DIR/check-fencing.sh"
