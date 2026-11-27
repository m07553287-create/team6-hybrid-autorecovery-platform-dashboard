#!/usr/bin/env bash
# s1 에서 실행(sudo 가능 사용자): 통합 콘솔을 /opt/figteam-console 에 설치하고 서비스로 띄운다.
#   사용: bash console/deploy/install.sh
# 콘솔 비밀번호는 설치 후 사용자가 직접: cd /opt/figteam-console && sudo .venv/bin/python -m console.setpass
set -euo pipefail
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
sudo install -d -o root -g root -m 755 /opt/figteam-console
sudo rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude 'tests' "$SRC/console/" /opt/figteam-console/console/
sudo install -d -o root -g user -m 750 /etc/figteam-console
[ -f /etc/figteam-console/env ] || { echo 'ALLOWED_ORIGIN=https://figteam.ktci5.kr' | sudo tee /etc/figteam-console/env >/dev/null; }
sudo chown root:user /etc/figteam-console/env; sudo chmod 640 /etc/figteam-console/env
sudo install -d -o user -g user -m 750 /var/log/figteam-console
[ -d /opt/figteam-console/.venv ] || sudo python3 -m venv /opt/figteam-console/.venv
sudo /opt/figteam-console/.venv/bin/pip install -q --upgrade pip
sudo /opt/figteam-console/.venv/bin/pip install -q fastapi 'uvicorn[standard]'
sudo install -m 644 /opt/figteam-console/console/deploy/figteam-console.service /etc/systemd/system/figteam-console.service
sudo systemctl daemon-reload
sudo systemctl enable --now figteam-console
sudo systemctl restart figteam-console
sleep 2
systemctl is-active figteam-console
grep -q '^CONSOLE_PASS_HASH=' /etc/figteam-console/env 2>/dev/null || sudo grep -q '^CONSOLE_PASS_HASH=' /etc/figteam-console/env || echo "※ 콘솔 비밀번호가 아직 없습니다: cd /opt/figteam-console && sudo .venv/bin/python -m console.setpass"
