#!/usr/bin/env bash
# s1 에서 실행: 저장소의 위키 코드를 wiki-01 에 올리고 서비스로 띄운다.
#   사용: bash wiki/deploy/install.sh [대상=ubuntu@172.20.0.50]
# 비밀값(TEAM_CREATE_CODE)은 이 스크립트가 다루지 않는다 — wiki-01 에서 직접 /etc/figteam-wiki/env 에 넣는다.
set -euo pipefail
TARGET="${1:-ubuntu@172.20.0.50}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar -C "$ROOT" --exclude='.venv' --exclude='__pycache__' --exclude='.seed' --exclude='wiki/tests' \
    -czf "$TMP/wiki.tgz" wiki tools/seed_wiki.py content/settings_guide.py content/scripts
scp -q "$TMP/wiki.tgz" "$TARGET:/tmp/wiki.tgz"
ssh "$TARGET" 'sudo bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/figteam-wiki
tar -xzf /tmp/wiki.tgz && rm -f /tmp/wiki.tgz
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q fastapi uvicorn
install -m 644 wiki/deploy/figteam-wiki.service /etc/systemd/system/figteam-wiki.service
install -m 755 wiki/deploy/backup.sh /usr/local/sbin/figteam-wiki-backup
echo '30 3 * * * root /usr/local/sbin/figteam-wiki-backup >> /var/log/figteam-wiki-backup.log 2>&1' > /etc/cron.d/figteam-wiki-backup
if [ ! -f /etc/figteam-wiki/env ]; then
  printf 'ALLOWED_ORIGIN=https://figteam.ktci5.kr\nTEAM_CREATE_CODE=\n' > /etc/figteam-wiki/env
  chown root:wiki /etc/figteam-wiki/env; chmod 640 /etc/figteam-wiki/env
  echo "※ /etc/figteam-wiki/env 의 TEAM_CREATE_CODE 를 직접 채우세요 (비어 있으면 팀 생성 불가)"
fi
systemctl daemon-reload
systemctl enable --now figteam-wiki
systemctl restart figteam-wiki
sleep 2
curl -fsS http://127.0.0.1:8080/api/health && echo
REMOTE
