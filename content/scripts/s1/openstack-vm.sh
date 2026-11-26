#!/usr/bin/env bash
# 원본: s1 ~/bin/openstack-vm.sh · 2026-11-26 실측 사본(읽기 전용, 비밀값 없음 확인)
set -e

CONF_FILE="/etc/openstack-active-vms.conf"

if [ -r "$CONF_FILE" ]; then
   mapfile -t VM_LIST < <(grep -v '^#' "$CONF_FILE" | grep -v '^[[:space:]]*$')
else
   VM_LIST=(
       "/home/user/vmware/openstack/openstack.vmx:192.168.120.160:Controller"
       "/home/user/vmware/compute1/compute1.vmx:192.168.120.161:Compute1"
       "/home/user/vmware/compute3/compute3.vmx:192.168.120.163:Compute3"
       "/home/user/vmware/compute4/compute4.vmx:192.168.120.164:Compute4"
   )
fi

GW_IP_OLD="192.168.59.2/24"
GW_IP_NEW="192.168.120.2/24"
NET_IF="vmnet8"

setup_net() {
   # 1. vmnet8 보조 IP 설정
   if ! ip addr show dev "$NET_IF" | grep -q "192.168.59.2"; then
       sudo ip addr add "$GW_IP_OLD" dev "$NET_IF" || true
   fi
   if ! ip addr show dev "$NET_IF" | grep -q "192.168.120.2"; then
       sudo ip addr add "$GW_IP_NEW" dev "$NET_IF" || true
   fi

   # 2. KT Edge WAF 연동용 MetalLB VIP (10.10.1.100) 수신 및 DNAT
   if ! ip addr show dev lo | grep -q "10.10.1.100"; then
       sudo ip addr add 10.10.1.100/32 dev lo || true
   fi
   if ! sudo iptables -t nat -C PREROUTING -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080 2>/dev/null; then
       sudo iptables -t nat -A PREROUTING -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080 || true
   fi
   if ! sudo iptables -t nat -C OUTPUT -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080 2>/dev/null; then
       sudo iptables -t nat -A OUTPUT -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080 || true
   fi

   # 3. VPN(10.10.10.0/24) 으로 가는 VM 응답은 wg0 대신 LAN(ER605) 경유
   if ! ip route show table 120 | grep -q "10.10.10.0/24"; then
       sudo ip route replace 10.10.10.0/24 via 192.168.100.1 dev wlp0s20f3 table 120 || true
   fi
   if ! ip rule show | grep -q "from 192.168.120.0/24 to 10.10.10.0/24 lookup 120"; then
       sudo ip rule add from 192.168.120.0/24 to 10.10.10.0/24 lookup 120 priority 1200 || true
   fi

   # 4. 게스트 인터넷 연결을 위한 NAT MASQUERADE 및 DNS DNAT 설정
   MAIN_DEV=$(ip route show default | awk '{print $5}' | head -n 1)
   if [ -n "$MAIN_DEV" ]; then
       for subnet in "192.168.59.0/24" "192.168.120.0/24"; do
           if ! sudo iptables -t nat -C POSTROUTING -s "$subnet" -o "$MAIN_DEV" -j MASQUERADE 2>/dev/null; then
               sudo iptables -t nat -A POSTROUTING -s "$subnet" -o "$MAIN_DEV" -j MASQUERADE || true
           fi
       done
       if ! sudo iptables -t nat -C PREROUTING -d 192.168.120.2 -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53 2>/dev/null; then
           sudo iptables -t nat -A PREROUTING -d 192.168.120.2 -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53 || true
       fi
       if ! sudo iptables -t nat -C PREROUTING -d 192.168.120.2 -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53 2>/dev/null; then
           sudo iptables -t nat -A PREROUTING -d 192.168.120.2 -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53 || true
       fi
   fi
}

start_vm() {
   setup_net
   local RUNNING
   RUNNING=$(vmrun list 2>/dev/null || true)
   for entry in "${VM_LIST[@]}"; do
       IFS=":" read -r vmx ip label <<< "$entry"
       local vm_dir
       vm_dir=$(dirname "$vmx")
       if [ -f "$vm_dir/.disabled" ]; then
           echo "[SKIP] $label is disabled ($vm_dir/.disabled exists)."
           continue
       fi
       if echo "$RUNNING" | grep -q "$vmx"; then
           echo "[INFO] $label is already running."
       else
           rm -rf "$vm_dir"/*.lck 2>/dev/null || true
           echo "[INFO] Starting $label ($vmx) in headless mode..."
           vmrun start "$vmx" nogui || true
           sleep 2
       fi
   done
}

stop_vm() {
   local target="$1"
   local RUNNING
   RUNNING=$(vmrun list 2>/dev/null || true)
   for (( idx=${#VM_LIST[@]}-1; idx>=0; idx-- )); do
       IFS=":" read -r vmx ip label <<< "${VM_LIST[idx]}"
       if [ -n "$target" ] && [[ "$label" != *"$target"* ]] && [[ "$vmx" != *"$target"* ]]; then
           continue
       fi
       if echo "$RUNNING" | grep -q "$vmx"; then
           echo "[INFO] Stopping $label ($vmx)..."
           vmrun stop "$vmx" soft 2>/dev/null || vmrun stop "$vmx" hard 2>/dev/null || true
       else
           echo "[INFO] $label is not running."
       fi
   done
}

disable_vm() {
   local target="$1"
   if [ -z "$target" ]; then
       echo "Usage: $0 disable <vm_name> (e.g. compute2)"
       exit 1
   fi
   local dir="/home/user/vmware/$target"
   if [ -d "$dir" ]; then
       touch "$dir/.disabled"
       echo "[OK] Disabled $target ($dir/.disabled created). Watchdog will NOT auto-restart it."
       stop_vm "$target"
   else
       echo "[ERROR] VM directory $dir not found."
       exit 1
   fi
}

enable_vm() {
   local target="$1"
   if [ -z "$target" ]; then
       echo "Usage: $0 enable <vm_name> (e.g. compute2)"
       exit 1
   fi
   local dir="/home/user/vmware/$target"
   if [ -f "$dir/.disabled" ]; then
       rm -f "$dir/.disabled"
       echo "[OK] Enabled $target ($dir/.disabled removed)."
   fi
}

status_vm() {
   echo "=== Running VMware VMs ==="
   vmrun list 2>/dev/null || true
   echo "=== Core Cluster Connectivity ==="
   for entry in "${VM_LIST[@]}"; do
       IFS=":" read -r vmx ip label <<< "$entry"
       local vm_dir
       vm_dir=$(dirname "$vmx")
       local dis=""
       if [ -f "$vm_dir/.disabled" ]; then
           dis=" [DISABLED]"
       fi
       if ping -c 1 -W 1 "$ip" >/dev/null 2>&1; then
           echo "  - $label ($ip): UP$dis"
       else
           echo "  - $label ($ip): DOWN$dis"
       fi
   done
   echo "=== MetalLB VIP (10.10.1.100) -> OpenStack minwon-app ==="
   if curl -sI --max-time 2 http://10.10.1.100:80/healthz >/dev/null 2>&1; then
       echo "  - VIP 10.10.1.100:80: READY (Routed to 192.168.120.226:30080)"
   else
       echo "  - VIP 10.10.1.100:80: FAILED"
   fi
}

case "$1" in
   start)
       start_vm
       ;;
   stop)
       stop_vm "$2"
       ;;
   restart)
       stop_vm
       sleep 3
       start_vm
       ;;
   status)
       status_vm
       ;;
   disable)
       disable_vm "$2"
       ;;
   enable)
       enable_vm "$2"
       ;;
   net)
       setup_net
       ;;
   *)
       echo "Usage: $0 {start|stop|restart|status|disable|enable|net}"
       exit 1
       ;;
esac
