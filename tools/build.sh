#!/usr/bin/env bash
# 기준본 → 배포본(backend/server.py) + Cloudflare Pages 화면(public/)
set -euo pipefail
cd "$(dirname "$0")/.."
python3 theme/apply_theme.py backend/server.base.py backend/server.py
python3 -m py_compile backend/server.py
python3 tools/export_public.py
# 비밀값 형태가 섞였는지 마지막 확인
if grep -rEn "[\"'][0-9a-f]{16,}[\"']" backend public functions >/dev/null; then
  echo "비밀값으로 보이는 문자열이 있습니다. 커밋하지 마세요." >&2; exit 1
fi
echo "build ok"
