#!/usr/bin/env bash
# 원본: aws-dr /opt/minwon-dr/check-fencing.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -euo pipefail
# A file is NEVER proof that the old primary is fenced.
# An operator must independently isolate on-prem writes and capture the final GTID.
echo 'BLOCKED: no independent on-prem fencing verifier is configured.' >&2
echo 'Required: externally verified fencing, immutable evidence and a fail-closed control-plane integration.' >&2
exit 1
