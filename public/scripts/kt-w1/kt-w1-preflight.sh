#!/bin/bash
# 원본: 이 가이드의 설계안 (/root/kt-w1-preflight.sh 로 저장해 실행) · 아직 적용 전
ok(){ echo "OK   $1"; }; ng(){ echo "FAIL $1"; FAIL=1; }
FAIL=0
[ "$(stat -fc %T /sys/fs/cgroup)" = cgroup2fs ] && ok "cgroup v2" || ng "cgroup v1 (kubelet-arg fail-cgroupv1=false 필요)"
swapon --show | grep -q . && ng "swap on" || ok "swap off"
[ "$(hostname)" != k8s-w1 ] && [ "$(hostname)" != k8s-cp1 ] && ok "hostname $(hostname)" || ng "hostname 중복"
timedatectl show -p NTPSynchronized --value | grep -q yes && ok "NTP" || ng "NTP 미동기"
ip -4 a show wg0 | grep -q 10.200.0.5 && ok "wg0 10.200.0.5" || ng "wg0 없음"
for t in 172.20.0.86:6443 172.20.0.180:30080 10.10.2.10:3306; do
  timeout 3 bash -c "</dev/tcp/${t%:*}/${t#*:}" 2>/dev/null && ok "tcp $t" || ng "tcp $t"; done
ping -c2 -W2 -M do -s 1342 172.20.0.86 >/dev/null && ok "MTU 1370 경로" || ng "MTU 1370 경로"
curl -sk -m5 https://172.20.0.86:6443/ping | grep -q pong && ok "API /ping" || ng "API /ping"
curl -s -m5 -o /dev/null https://ghcr.io && ok "인터넷(ghcr)" || ng "인터넷(ghcr)"
exit $FAIL
