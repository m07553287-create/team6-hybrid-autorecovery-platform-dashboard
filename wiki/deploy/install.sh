#!/usr/bin/env bash
# s1 에서 실행: 위키 코드를 wiki-01 에 올리고 Redis·서비스를 설정한다.
#   사용: bash wiki/deploy/install.sh [대상=ubuntu@192.168.120.230]
# 비밀값: Redis 비밀번호는 wiki-01 안에서 무작위 생성(밖으로 나가지 않음). TEAM_CREATE_CODE 는 사용자가 직접 입력.
set -euo pipefail
TARGET="${1:-ubuntu@192.168.120.230}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
tar -C "$ROOT" --exclude='.venv' --exclude='__pycache__' --exclude='.seed' --exclude='wiki/tests' \
    -czf "$TMP/wiki.tgz" wiki tools/seed_wiki.py content/settings_guide.py content/scripts
scp -q "$TMP/wiki.tgz" "$TARGET:/tmp/wiki.tgz"
ssh "$TARGET" 'sudo bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/figteam-wiki
tar -xzf /tmp/wiki.tgz && rm -f /tmp/wiki.tgz
# --- Redis: 위키 전용 설정 + 비밀번호(최초 1회 생성) ---
install -m 640 -o redis -g redis wiki/deploy/redis-figteam.conf /etc/redis/figteam.conf
if [ ! -f /etc/redis/figteam-pass.conf ]; then
  PASS="$(openssl rand -hex 24)"
  printf 'requirepass %s\n' "$PASS" > /etc/redis/figteam-pass.conf
  chown redis:redis /etc/redis/figteam-pass.conf; chmod 600 /etc/redis/figteam-pass.conf
  printf 'ALLOWED_ORIGIN=https://figteam.ktci5.kr\nREDIS_URL=redis://127.0.0.1:6379/0\nREDIS_PASSWORD=%s\nTEAM_CREATE_CODE=\n' "$PASS" > /etc/figteam-wiki/env
  chown root:wiki /etc/figteam-wiki/env; chmod 640 /etc/figteam-wiki/env
  unset PASS
  echo "※ /etc/figteam-wiki/env 의 TEAM_CREATE_CODE 를 직접 채우세요 (비어 있으면 팀 생성 불가)"
fi
grep -q '^include /etc/redis/figteam.conf' /etc/redis/redis.conf || echo 'include /etc/redis/figteam.conf' >> /etc/redis/redis.conf
systemctl enable --now redis-server && systemctl restart redis-server
# --- 앱 ---
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q fastapi uvicorn redis
install -m 644 wiki/deploy/figteam-wiki.service /etc/systemd/system/figteam-wiki.service
install -m 755 wiki/deploy/backup.sh /usr/local/sbin/figteam-wiki-backup
echo '30 3 * * * root /usr/local/sbin/figteam-wiki-backup >> /var/log/figteam-wiki-backup.log 2>&1' > /etc/cron.d/figteam-wiki-backup
systemctl daemon-reload
systemctl enable --now figteam-wiki
systemctl restart figteam-wiki
sleep 2
curl -fsS http://127.0.0.1:8080/api/health && echo
REMOTE
