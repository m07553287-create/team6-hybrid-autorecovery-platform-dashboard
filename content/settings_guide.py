# -*- coding: utf-8 -*-
"""figteam.ktci5.kr [설정] 화면 원본 데이터.

- 2026-11-26 s1(10.10.10.8)·OpenStack·k3s·KT Edge·AWS dr 실측을 기준으로 쓴다.
- 이 파일을 고친 뒤 `tools/build.sh` 를 돌리면 backend/server.py 와 public/index.html 에 반영된다.
- 비밀값(토큰·비밀번호·WG 개인키)은 절대 넣지 않는다. 값 대신 "읽는 명령"만 적는다.

상태 표시
  live   : 실측으로 확인한 현재 구성
  design : 설계안(아직 적용 안 함) — 적용 전 계획·영향 범위 확인 필요
  nolook : 실측하지 못함(접속 불가 등) — 문서·외부 응답 기준
"""

MEASURED = "2026-11-26"

# ---------------------------------------------------------------------------
# 공통 변수표 — 명령어 안의 값이 여기서 나온다. 값이 바뀌면 '바뀌면 확인' 열을 본다.
# ---------------------------------------------------------------------------
VARIABLES = [
    # 변수, 값, 사용처, 바뀌면 확인할 곳
    ["S1_UPLINK", "192.168.100.151 (wlp0s20f3, DHCP)", "s1 인터넷 출구 · MASQUERADE 출구 장치", "openstack-vm.sh 의 MAIN_DEV 자동 감지 → `sudo systemctl restart openstack-vmnet`"],
    ["HOME_PUBLIC_IP", "175.196.197.51 (집·강의장 회선, 바뀜)", "KT 허브가 보는 s1 WG 출발지", "s1이 keepalive 로 먼저 붙으므로 KT 쪽 수정 불필요. 핸드셰이크만 확인"],
    ["S1_VMNET8_GW", "192.168.120.2/24", "ext-net 게이트웨이 · VM DNS(53→8.8.8.8 DNAT)", "ext-subnet gateway_ip, openstack-vm.sh GW_IP_NEW"],
    ["OS_CONTROLLER", "192.168.120.160", "Keystone·Nova·Neutron(OVN)·Horizon", "s1 osx 래퍼, cloudflared horizon 라우트"],
    ["OS_COMPUTE", "161 compute1 · 163 compute3 · 164 compute4 (162 compute2 = down/삭제)", "하이퍼바이저", "`openstack hypervisor list`, ssh_known_hosts(마이그레이션)"],
    ["RT_EDGE_EXT", "192.168.120.202 (SNAT ON)", "s1 → 172.20.0.0/24 정적 라우트 next-hop", "datanet-route.conf 의 `ip route replace 172.20.0.0/24 via …`"],
    ["RT_DATA_EXT", "192.168.120.220 (SNAT OFF)", "s1 → 10.10.2.0/24 정적 라우트 next-hop", "datanet-route.conf 의 `ip route replace 10.10.2.0/24 via …`"],
    ["FIP_CP1", "192.168.120.226 → 172.20.0.86", "VIP DNAT 대상 · cloudflared argocd/grafana · KT 6443 DNAT", "openstack-vm.sh 34~38행, KT `iptables -t nat` 6443, cloudflared config"],
    ["FIP_FREE", "192.168.120.201 · .216 (미할당)", "w1 등 추가 노드 외부 IP 후보", "-"],
    ["CP1 / W1 / DB", "172.20.0.86 / 172.20.0.180 / 10.10.2.10", "k3s 서버 / k3s 에이전트 / MySQL Primary", "앱 env DB_HOST, sg-db, MySQL 계정 host"],
    ["VIP_APP", "10.10.1.100 (s1 lo) :80 → 192.168.120.226:30080", "KT Edge upstream minwon_backend", "KT `/etc/nginx/conf.d/upstream.conf`(switch_edge.yml 관리)"],
    ["WG_NET", "10.200.0.0/24 · .1 KT허브 · .2 s1 · .3 aws-ctl · .4 aws-dr · .5 kt-w1(예약)", "3사 간 East-West", "각 노드 wg 설정 AllowedIPs"],
    ["KT_EDGE", "공인 14.63.212.190 · 사설 172.27.0.160/16", "인입·WAF·WG 허브", "KT 콘솔 포트포워딩(TCP 22·80·443·30080 / UDP 51820)"],
    ["AWS_DR", "사설 10.51.1.165 · 공인 54.116.129.147 · t3.small", "DR k3s + MySQL 복제본", "KT 허브 peer Endpoint"],
    ["AWS_CTL", "사설 10.50.1.85 · 공인: 노션 13.125.163.58 / 허브 실측 13.124.253.30", "Recovery Orchestrator :8080", "공인 IP가 바뀐 흔적 → EIP·키페어 확인"],
    ["K3S_VERSION", "v1.37.2+k3s1 (온프렘·AWS 동일)", "에이전트 조인 버전 고정", "INSTALL_K3S_VERSION"],
    ["POD / SVC CIDR", "10.42.0.0/16 / 10.43.0.0/16 (k3s 기본)", "flannel VXLAN · ClusterIP", "다른 사이트 대역과 겹치면 안 됨"],
    ["MTU", "OVN 1442 · WG 1420 · cp1 flannel.1 1392", "터널 중첩 단편화", "`ip link`, `ping -M do -s`"],
    ["APP NodePort", "30080 (minwon-app-svc)", "VIP DNAT · KT Edge", "Service spec.ports.nodePort"],
]

# ---------------------------------------------------------------------------
# 선행 순서 — 아래 순서를 지켜야 다음 단계의 명령이 오류 없이 돈다.
# ---------------------------------------------------------------------------
STEPS = [
    {"no": "S0", "title": "접속 경로 확보", "where": "맥", "page": "inst-s1", "area": "access",
     "why": "모든 작업은 s1(10.10.10.8)을 거친다. OpenStack·k8s·db·AWS 노드에 공인 SSH 가 없다.",
     "gate": "ssh user@10.10.10.8 hostname   # t1-vm2\nssh root@14.63.212.190 hostname # kt-edge-dr-01"},
    {"no": "S1", "title": "s1 호스트 기반 (VMware·vmnet8·NAT)", "where": "s1", "page": "inst-s1", "area": "vmnet",
     "why": "OpenStack VM 4대가 vmnet8(192.168.120.0/24) 위에 있다. 게이트웨이 .2 와 MASQUERADE 가 없으면 VM 이 인터넷·DNS 를 못 쓴다.",
     "gate": "ip -br a show vmnet8 | grep 192.168.120.2\nsysctl net.ipv4.ip_forward   # = 1"},
    {"no": "S2", "title": "OpenStack 노드 기동·서비스 확인", "where": "s1 → controller", "page": "inst-controller", "area": "svc",
     "why": "nova-compute·OVN 에이전트가 up 이어야 서버 생성·FIP 가 동작한다.",
     "gate": "~/bin/osx 160 \"source /root/keystonerc_admin; openstack compute service list\""},
    {"no": "S3", "title": "OpenStack 네트워크·라우터·SG·Flavor·이미지", "where": "controller", "page": "inst-controller", "area": "net",
     "why": "라우터 외부 IP(.202/.220)가 정해져야 s1 정적 라우트를 걸 수 있다.",
     "gate": "openstack router list\nopenstack router show rt-edge -c external_gateway_info"},
    {"no": "S4", "title": "s1 정적 라우트·VIP DNAT", "where": "s1", "page": "inst-s1", "area": "vmnet",
     "why": "s1 이 172.20.0.0/24·10.10.2.0/24 로 가는 길을 알아야 WG 너머(KT·AWS)에서 온프렘에 닿는다.",
     "gate": "ip r | grep -E '172.20.0.0|10.10.2.0'\ncurl -sI http://10.10.1.100/healthz"},
    {"no": "S5", "title": "WireGuard 허브-스포크 (KT 허브 ↔ s1 ↔ AWS)", "where": "KT·s1·AWS", "page": "inst-ktedge", "area": "wg",
     "why": "KT 허브 10.200.0.1 이 모든 피어를 잇는다. 허브 AllowedIPs 에 온프렘 대역이 있어야 AWS·KT 가 온프렘으로 간다.",
     "gate": "wg show   # 모든 peer latest handshake < 2분"},
    {"no": "S6", "title": "VM 생성 (db-01 → k8s-cp1 + FIP → k8s-w1)", "where": "controller", "page": "inst-controller", "area": "server",
     "why": "DB 를 먼저 띄워야 앱 배포 시 DB_HOST 가 응답한다.",
     "gate": "openstack server list --all-projects   # 3대 ACTIVE"},
    {"no": "S7", "title": "db-01 MySQL 8.4 · 볼륨 · 백업", "where": "db-01", "page": "inst-db01", "area": "mysql",
     "why": "GTID·binlog 가 켜져 있어야 AWS 복제본이 붙는다.",
     "gate": "sudo mysql -e \"select @@gtid_mode,@@read_only\"   # ON, 0"},
    {"no": "S8", "title": "k3s 서버(cp1) → 에이전트(w1) → 앱·HPA·PDB·ArgoCD", "where": "cp1·w1", "page": "inst-cp1", "area": "k3s",
     "why": "metrics-server 가 있어야 HPA 가 동작하고, PDB 가 있어야 drain 때 서비스가 유지된다.",
     "gate": "kubectl get nodes   # 2 Ready\nkubectl -n minwon-sample get hpa,pdb"},
    {"no": "S9", "title": "KT Edge nginx·WAF upstream → VIP", "where": "KT", "page": "inst-ktedge", "area": "nginx",
     "why": "공개 진입(minwon.ktci5.kr)은 KT 하나. upstream 이 VIP 10.10.1.100 을 가리켜야 한다.",
     "gate": "nginx -t && curl -s -o /dev/null -w '%{http_code}' -H 'Host: minwon.ktci5.kr' http://127.0.0.1/"},
    {"no": "S10", "title": "AWS dr k3s · MySQL 복제 · 역터널 / ctl Orchestrator", "where": "AWS", "page": "inst-awsdr", "area": "mysql",
     "why": "평시 복제 지연 0 을 유지해야 L3 승격 시 RPO 가 0 에 가깝다.",
     "gate": "Replica_IO_Running: Yes / Replica_SQL_Running: Yes / Seconds_Behind_Source: 0"},
    {"no": "S11", "title": "Cloudflare Tunnel 라우트 (s1)", "where": "s1", "page": "inst-s1", "area": "cfd",
     "why": "figteam·horizon·kt-edge·aws-ctl 콘솔은 인바운드 포트 없이 터널로만 공개한다.",
     "gate": "cloudflared tunnel ingress rule https://figteam.ktci5.kr --config /etc/cloudflared/config.yml"},
    {"no": "S12", "title": "KT 워커 kt-w1 조인 (HA) → HPA 확장 → 버스팅", "where": "KT·controller·cp1", "page": "inst-ktw1", "area": "pre",
     "why": "S1~S11 이 모두 정상이어야 조인 단계에서 막히지 않는다. 제약 12개를 먼저 제거한다.",
     "gate": "bash /root/kt-w1-preflight.sh   # 모든 항목 OK 일 때만 조인"},
]

# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------
PAGES = {}

# ===================== 시작하기: 개요 =====================
PAGES["overview"] = {
    "kind": "doc",
    "title": "전체 구성과 변수표",
    "tag": "실측 " + MEASURED,
    "desc": "온프렘(s1 노트북 위 VMware → OpenStack) · KT Cloud · AWS 를 WireGuard 허브(KT)로 묶은 구성이다. 아래 경로도와 변수표가 모든 페이지 명령어의 기준값이다.",
    "blocks": [
        {"type": "h", "text": "트래픽 경로 (실측)"},
        {"type": "code", "label": "외부 요청 → 앱 → DB", "code": r"""사용자
  │ https://minwon.ktci5.kr  (Cloudflare 프록시)
  ▼
KT Edge kt-edge-dr-01  14.63.212.190 / 172.27.0.160
  nginx :80/:443 → 127.0.0.1:8081 (ModSecurity WAF, 20r/s)
  upstream minwon_backend = 10.10.1.100:80
  │ WireGuard wg0 10.200.0.1  ──(UDP 51820)──▶  s1 wg-kt 10.200.0.2
  ▼
s1 (Ubuntu 26.04, t1-vm2)
  lo 10.10.1.100  → iptables DNAT → 192.168.120.226:30080
  │ vmnet8 192.168.120.0/24
  ▼
OpenStack rt-edge (FIP 192.168.120.226 ↔ 172.20.0.86)
  ▼
k8s-cp1 NodePort 30080 → Service minwon-app-svc → 파드 ×2 (현재 둘 다 k8s-w1)
  │ DB_HOST=10.10.2.10  (172.20.0.0/24 → host route 10.10.2.0/24 via 172.20.0.125 = rt-data)
  ▼
db-01 MySQL 8.4 Primary (GTID)  ──복제──▶ AWS dr minwon-mysql-0 (read_only=1)
                                  (dr 의 port-forward 10.200.0.4:13306 역터널)"""},
        {"type": "code", "label": "관리 콘솔 (Cloudflare Tunnel, s1 에서 아웃바운드)", "code": r"""figteam.ktci5.kr      → https://m07553287-create.github.io (GitHub Pages, 이 화면)
figteam-api.ktci5.kr  → 127.0.0.1:18088 (s1 figteam-portal)
horizon.ktci5.kr      → 192.168.120.160:80
kt-edge.ktci5.kr      → 10.200.0.1:8088 (KT 상태 vhost, WG 전용)
aws-ctl.ktci5.kr      → 10.200.0.3:8080 (Recovery Orchestrator)
argocd.ktci5.kr       → 192.168.120.226:30800  ※ 실측: argocd-server replicas 0, 30800 서비스 없음
grafana.ktci5.kr      → 192.168.120.226:30300  ※ 실측: 30300 서비스 없음"""},
        {"type": "h", "text": "공통 변수표"},
        {"type": "vars"},
        {"type": "h", "text": "표시 규칙"},
        {"type": "legend"},
    ],
}

# ===================== 시작하기: 선행 순서 =====================
PAGES["steps"] = {
    "kind": "doc",
    "title": "선행 항목과 진행 순서",
    "tag": "S0 → S12",
    "desc": "각 단계의 '통과 조건'이 나와야 다음 단계로 간다. 통과 조건이 안 나오면 해당 인스턴스 페이지의 '오류 시 확인' 표로 간다.",
    "blocks": [{"type": "steps"}],
}

# ===================== 온프렘: s1 =====================
PAGES["inst-s1"] = {
    "kind": "instance",
    "cloud": "onprem",
    "title": "s1 온프렘 호스트",
    "tag": "t1-vm2 · 10.10.10.8",
    "status": "live",
    "steps": "S0 · S1 · S4 · S5 · S11",
    "desc": "GPU 노트북의 Ubuntu. VMware Workstation 으로 OpenStack 노드 4대를 띄우고, vmnet8 게이트웨이·NAT·정적 라우트·WireGuard·Cloudflare Tunnel 을 맡는다. 온프렘의 모든 외부 연결이 이 호스트 하나를 지난다(단일 장애점).",
    "specs": [
        ["OS / 커널", "Ubuntu 26.04.1 LTS / 7.0.0-44"], ["CPU / RAM", "20 vCPU / 30 GiB"],
        ["디스크", "/ 466G (사용 53%)"], ["업링크", "wlp0s20f3 192.168.100.151 (Wi-Fi, DHCP)"],
        ["vmnet8", "192.168.120.2/24 · 172.16.180.1/24"], ["WG", "wg-kt 10.200.0.2/24 · wg0 10.10.10.8/32"],
    ],
    "areas": [
        {
            "id": "access", "name": "접속 경로", "status": "live",
            "design": [
                "맥 → s1 은 WG wg0(10.10.10.0/24, 집 공유기 51820)로 들어온다.",
                "s1 → OpenStack 노드는 root 키 접속. `~/bin/osx <끝자리> \"<명령>\"` 래퍼로 통일한다.",
                "AWS 노드는 공인 22 가 보안그룹(admin_cidrs)으로 막혀 있어 s1(WG 10.200.0.2) 경유만 된다.",
            ],
            "config": [
                {"label": "~/.ssh/config (맥)", "code": r"""Host s1
    HostName 10.10.10.8
    User user
Host cp1
    HostName 192.168.120.226
    User ubuntu
    ProxyJump s1
Host w1
    HostName 172.20.0.180
    User ubuntu
    ProxyJump s1
Host db-01
    HostName 10.10.2.10
    User ubuntu
    ProxyJump s1
Host dr
    HostName 10.200.0.4
    User rocky
    IdentityFile ~/.ssh/minwon-key.pem
    IdentitiesOnly yes
    ProxyJump s1
Host kt-edge
    HostName 14.63.212.190
    User root"""},
                {"label": "s1 ~/bin/osx (OpenStack 노드 root 실행 래퍼)", "code": r"""#!/bin/sh
# osx <last-octet> "<cmd>"
h=$1; shift
exec ssh -n -q -o BatchMode=yes -o ConnectTimeout=8 \
  -o StrictHostKeyChecking=accept-new -o LogLevel=ERROR root@192.168.120.$h "$@" """},
            ],
            "commands": [
                {"cat": "조회", "label": "노드별 접속 확인", "code": r"""ssh s1 hostname                         # t1-vm2
ssh s1 '~/bin/osx 160 hostname'         # controller
ssh cp1 hostname; ssh w1 hostname; ssh db-01 hostname
ssh dr hostname                         # ip-10-51-1-165...
ssh kt-edge hostname                    # kt-edge-dr-01"""},
            ],
            "verify": [
                {"label": "전 구간 한 번에", "code": r"""for h in s1 cp1 w1 db-01 dr kt-edge; do printf '%-8s ' $h; ssh -o ConnectTimeout=8 $h hostname 2>&1 | tail -1; done""", "expect": "6줄 모두 호스트명 출력"},
            ],
            "trouble": [
                ["ssh s1 타임아웃", "맥 WG wg0 / 집 공인 IP", "맥: `sudo wg show` 핸드셰이크 · s1: `sudo wg show wg0`", "공유기 51820 포워딩, s1 Endpoint(175.196.197.51) 확인"],
                ["cp1/w1 Permission denied", "Nova keypair", "controller: `openstack server show k8s-cp1 -c key_name`", "cp1 은 figteam-key·s1-ktci5, w1 은 figteam-key(/root/figteam-key.pem on controller)만 붙어 있음 → cp1 경유 ProxyJump"],
                ["aws-ctl Permission denied (실측)", "ctl 키페어 / 공인 IP 변경", "KT 허브 `wg show` 의 ctl Endpoint(13.124.253.30)와 노션 기록(13.125.163.58) 비교", "ctl 재생성 여부·키페어 이름 확인 후 SSM Session Manager 로 접속(무-SSH 설계)"],
            ],
        },
        {
            "id": "vmnet", "name": "VMware·vmnet8·NAT·라우팅", "status": "live",
            "design": [
                "VMware vmnet8(NAT) 위에 별칭 192.168.120.2/24 를 얹어 OpenStack ext-net(flat, physnet extnet) 게이트웨이로 쓴다.",
                "VM 의 인터넷은 s1 MASQUERADE(-s 192.168.120.0/24 -o 업링크), DNS 는 192.168.120.2:53 → 8.8.8.8 DNAT.",
                "OpenStack 내부망 2개는 라우터 외부 IP 로 정적 라우트: 172.20.0.0/24 → .202(rt-edge), 10.10.2.0/24 → .220(rt-data).",
                "KT Edge 가 보는 앱 주소는 VIP 10.10.1.100(lo). PREROUTING/OUTPUT DNAT 로 cp1 FIP:30080 에 넘긴다.",
                "맥(10.10.10.0/24)으로 가는 응답은 정책 라우팅 table 120 으로 공유기에 보낸다.",
                "모두 `openstack-vm.service`(start)와 `openstack-vmnet.service`(net, 라우트 drop-in)가 부팅 때 다시 건다.",
            ],
            "config": [
                {"label": "/etc/systemd/system/openstack-vmnet.service.d/datanet-route.conf", "code": r"""[Service]
# OpenStack data-net(db-01) → rt-data ext IP
ExecStartPost=/usr/sbin/ip route replace 10.10.2.0/24 via 192.168.120.220 dev vmnet8
# OpenStack figteam-net(k8s-cp1, k8s-w1) → rt-edge ext IP
ExecStartPost=/usr/sbin/ip route replace 172.20.0.0/24 via 192.168.120.202 dev vmnet8"""},
                {"label": "~/bin/openstack-vm.sh net (핵심부)", "code": r"""ip addr add 192.168.120.2/24 dev vmnet8                 # ext-net 게이트웨이
ip addr add 10.10.1.100/32 dev lo                        # KT Edge 용 VIP
iptables -t nat -A PREROUTING -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080
iptables -t nat -A OUTPUT     -d 10.10.1.100 -p tcp --dport 80 -j DNAT --to-destination 192.168.120.226:30080
ip route replace 10.10.10.0/24 via 192.168.100.1 dev wlp0s20f3 table 120
ip rule add from 192.168.120.0/24 to 10.10.10.0/24 lookup 120 priority 1200
iptables -t nat -A POSTROUTING -s 192.168.120.0/24 -o $MAIN_DEV -j MASQUERADE
iptables -t nat -A PREROUTING -d 192.168.120.2 -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53"""},
            ],
            "commands": [
                {"cat": "적용", "label": "네트워크 재적용 / VM 기동·정지", "code": r"""sudo systemctl restart openstack-vmnet      # 별칭·NAT·라우트 재적용
~/bin/openstack-vm.sh start                 # controller → compute1·3·4 순서 기동
~/bin/openstack-vm.sh status                # VM·VIP 상태
~/bin/openstack-vm.sh stop                  # soft → hard"""},
                {"cat": "조회", "label": "현재 상태", "code": r"""vmrun list
ip -br a; ip r
sudo iptables -t nat -S | grep -vE '^-N|KUBE|CNI|FLANNEL|DOCKER'
ip rule show | grep 1200
grep -E '^(memsize|numvcpus)' ~/vmware/*/*.vmx"""},
            ],
            "verify": [
                {"label": "VIP → 앱", "code": "curl -sI http://10.10.1.100/healthz | head -1", "expect": "HTTP/1.1 200"},
                {"label": "내부망 도달", "code": "ping -c2 172.20.0.86; ping -c2 10.10.2.10", "expect": "응답 (db-01 ICMP 는 sg-db 가 192.168.120.2 에 22/3306 만 허용 → ping 실패는 정상일 수 있음)"},
            ],
            "trouble": [
                ["VM 이 인터넷/apt 불가", "S1_UPLINK (Wi-Fi 재연결로 장치·IP 변경)", "`ip route show default` · `sudo iptables -t nat -S POSTROUTING`", "`sudo systemctl restart openstack-vmnet` (MAIN_DEV 재감지)"],
                ["KT/AWS → 172.20.x 불통", "RT_EDGE_EXT / RT_DATA_EXT", "`ip r | grep 172.20` · controller: `openstack router show rt-edge -c external_gateway_info`", "라우터를 다시 만들어 외부 IP 가 바뀌었으면 datanet-route.conf 수정 → daemon-reload → restart"],
                ["VIP 10.10.1.100 502/timeout", "FIP_CP1 / NodePort", "`curl -sI http://192.168.120.226:30080/healthz` · `kubectl -n minwon-sample get svc`", "FIP 가 바뀌었으면 openstack-vm.sh 34~38행·KT 6443 DNAT·cloudflared 동시 수정"],
                ["nat 규칙이 2벌씩 보임 (실측)", "수동 실행 + 서비스 실행 중복", "`sudo iptables -t nat -S | sort | uniq -d`", "동작엔 영향 없음. 정리 시 `-D` 로 한 벌만 삭제(서비스 재시작 때 -C 검사로 다시 늘지 않음)"],
                ["VM 기동 실패 / vmnet 권한", "/dev/vmnet8 권한", "`ls -l /dev/vmnet8`", "drop-in 의 `chgrp user /dev/vmnet8 && chmod g+rw` 확인 → `sudo systemctl restart vmware`"],
            ],
        },
        {
            "id": "wg", "name": "WireGuard (wg-kt · wg0)", "status": "live",
            "design": [
                "wg-kt: KT 허브 하나만 peer. AllowedIPs 10.200.0.0/24 + KT·AWS VPC(172.27/16, 10.50/16, 10.30/16) → 3사 대역이 전부 허브로 간다.",
                "s1 은 NAT 뒤(집 회선)라 Endpoint 를 쓰지 않고 PersistentKeepalive 25 로 먼저 붙는다. 집 공인 IP 가 바뀌어도 허브가 따라온다.",
                "wg0: 맥 관리용(10.10.10.0/24). 서비스 트래픽과 분리.",
                "MTU 1420(기본). OVN 1442 위를 지나는 VXLAN 이 이 구간에서 단편화될 수 있다 → KT 워커 조인 시 C6 참고.",
            ],
            "config": [
                {"label": "/etc/wireguard/wg-kt.conf", "code": r"""[Interface]
Address = 10.200.0.2/24
PrivateKey = <s1 개인키 - 파일에만 둔다>

[Peer]
# KT Cloud Edge-GW Hub (kt-edge-dr-01)
PublicKey = <KT 허브 공개키: KT 에서 `wg show wg0 public-key`>
Endpoint = 14.63.212.190:51820
AllowedIPs = 10.200.0.0/24, 10.30.0.0/16, 10.50.0.0/16, 172.27.0.0/16
PersistentKeepalive = 25"""},
            ],
            "commands": [
                {"cat": "조회", "label": "터널 상태", "code": r"""sudo wg show wg-kt | grep -E 'endpoint|allowed|handshake|transfer'
systemctl is-enabled wg-quick@wg-kt wg-quick@wg0"""},
                {"cat": "적용", "label": "설정 변경 후 안전 재시작 (3분 자동 되돌리기)", "code": r"""sudo cp /etc/wireguard/wg-kt.conf /root/wg-kt.conf.bak
# 먼저 되돌리기 타이머를 건다 — 터널이 끊겨도 3분 뒤 원복
sudo systemd-run --on-active=180 --unit=wg-rollback /bin/sh -c \
  'cp /root/wg-kt.conf.bak /etc/wireguard/wg-kt.conf && systemctl restart wg-quick@wg-kt'
sudo systemctl restart wg-quick@wg-kt
ping -c3 10.200.0.1 && sudo systemctl stop wg-rollback.timer   # 정상이면 취소"""},
            ],
            "verify": [
                {"label": "허브·AWS 도달", "code": "ping -c2 10.200.0.1; ping -c2 10.200.0.4", "expect": "응답, handshake < 2분"},
            ],
            "trouble": [
                ["handshake 가 2분 이상 멈춤", "KT 포트포워딩 UDP 51820 / 허브 peer 키", "KT: `wg show wg0` 에서 s1 peer 의 endpoint·handshake", "KT 콘솔 포트포워딩·방화벽, 허브 peer 공개키 일치 확인"],
                ["`wg syncconf` 후 터널 멈춤", "운영 금지 명령", "`journalctl -u wg-quick@wg-kt -n 50`", "syncconf 대신 위 '안전 재시작' 절차만 쓴다 (11-19 ctl 20분 단절 사례)"],
                ["특정 대역만 불통", "AllowedIPs 누락/중복", "`ip r | grep wg-kt` · 허브 쪽 AllowedIPs", "대역은 한 peer 에만. 허브 s1-peer 에 온프렘 대역 3개(192.168.120/24·172.20.0/24·10.10.2/24)가 있어야 함"],
            ],
        },
        {
            "id": "cfd", "name": "Cloudflare Tunnel", "status": "live",
            "design": [
                "인바운드 포트 없이 s1 의 cloudflared 가 Cloudflare 로 아웃바운드 연결. 공개 진입(minwon)은 KT 하나만 둔다(앱 직통 openstack/app 호스트는 11-18 제거).",
                "figteam.ktci5.kr 은 GitHub Pages 를 오리진으로 프록시(httpHostHeader 고정).",
            ],
            "config": [
                {"label": "/etc/cloudflared/config.yml (ingress 부분)", "code": r"""tunnel: <터널 UUID>
ingress:
  - hostname: figteam-api.ktci5.kr
    service: http://127.0.0.1:18088
  - hostname: figteam.ktci5.kr
    service: https://m07553287-create.github.io
    originRequest:
      httpHostHeader: figteam.ktci5.kr
  - hostname: argocd.ktci5.kr
    service: http://192.168.120.226:30800
  - hostname: grafana.ktci5.kr
    service: http://192.168.120.226:30300
  - hostname: horizon.ktci5.kr
    service: http://192.168.120.160:80
  - hostname: kt-edge.ktci5.kr
    service: http://10.200.0.1:8088
  - hostname: aws-ctl.ktci5.kr
    service: http://10.200.0.3:8080
  - service: http_status:404"""},
            ],
            "commands": [
                {"cat": "조회", "label": "라우트 검사", "code": r"""sudo cloudflared tunnel ingress validate --config /etc/cloudflared/config.yml
sudo cloudflared tunnel ingress rule https://aws-ctl.ktci5.kr --config /etc/cloudflared/config.yml
systemctl status cloudflared --no-pager | head -5"""},
                {"cat": "적용", "label": "변경 반영", "code": "sudo systemctl restart cloudflared"},
            ],
            "verify": [
                {"label": "오리진 응답", "code": r"""curl -s -o /dev/null -w '%{http_code}\n' http://10.200.0.1:8088/
curl -s http://10.200.0.3:8080/healthz""", "expect": "200 / Orchestrator 응답"},
            ],
            "trouble": [
                ["argocd/grafana 502 (실측)", "백엔드 없음", "cp1: `kubectl -n argocd get deploy argocd-server` (0/0) · `kubectl get svc -A | grep -E '30800|30300'`", "argocd-server 를 1로 올리고 NodePort 30800 서비스 생성, 또는 라우트 삭제"],
                ["figteam.ktci5.kr 옛 화면", "Cloudflare·Pages 캐시(max-age=600)", "`curl -sI https://figteam.ktci5.kr | grep -E 'age|last-modified'`", "Actions 배포 완료 확인 후 10분 대기 또는 Cloudflare 캐시 퍼지"],
                ["DNS 레코드가 엉뚱한 존에 생김", "cert.pem 존 = ktci5.kr", "`cloudflared tunnel route dns` 사용 존 확인", "ktci5.kr 외 존은 API 토큰으로 DNS 수정"],
            ],
        },
    ],
}

# ===================== OpenStack: controller =====================
PAGES["inst-controller"] = {
    "kind": "instance",
    "cloud": "openstack",
    "title": "OpenStack controller (+compute)",
    "tag": "192.168.120.160",
    "status": "live",
    "steps": "S2 · S3 · S6",
    "desc": "Packstack/RDO 단일 컨트롤러. Neutron 은 OVN. 인스턴스는 올리지 않고 compute1·3·4 에 배치한다. admin rc 로 전체를, figteam rc 로 프로젝트 자원을 다룬다.",
    "specs": [
        ["OS", "CentOS Stream 9"], ["VM 크기", "4 vCPU / 10 GB (s1 VMware)"],
        ["CLI", "openstack 6.6.1"], ["Neutron", "OVN (Geneve, MTU 1442)"],
        ["compute", "1 (4G·k8s-w1) · 3 (6G·k8s-cp1) · 4 (6G·db-01) · 2 down"], ["rc 파일", "/root/keystonerc_admin · keystonerc_figteam"],
    ],
    "areas": [
        {
            "id": "svc", "name": "서비스·하이퍼바이저", "status": "live",
            "design": [
                "nova-compute 와 OVN Controller Gateway/Metadata 에이전트가 각 compute 에서 up 이어야 스케줄·메타데이터·FIP 가 동작한다.",
                "compute2 는 VM 을 지웠지만 서비스 레코드가 남아 down 으로 보인다(실측). 스케줄 대상에서 빼 둔다.",
            ],
            "config": [],
            "commands": [
                {"cat": "조회", "label": "상태 점검", "code": r"""ssh s1
~/bin/osx 160 "source /root/keystonerc_admin
openstack compute service list -c Binary -c Host -c State
openstack network agent list -c 'Agent Type' -c Host -c Alive
openstack hypervisor list"""},
                {"cat": "적용", "label": "compute2 잔존 레코드 비활성 (삭제 전 단계)", "code": r"""openstack compute service set --disable --disable-reason removed compute2 nova-compute
# 완전 삭제는 되돌릴 수 없으니 확인 후:  openstack compute service delete <id>"""},
                {"cat": "설치", "label": "compute 노드 추가 (요약)", "code": r"""# compute2 VM clone → hostname/IP 변경 → infra/openstack/add-compute/ 스크립트
# 콜드 마이그레이션을 쓰려면 새 노드 호스트키를 5대 모두의 /etc/ssh/ssh_known_hosts 에 넣는다
nova-manage cell_v2 discover_hosts --verbose"""},
            ],
            "verify": [
                {"label": "가동 compute 3대", "code": "openstack hypervisor list -c 'Hypervisor Hostname' -c State", "expect": "compute1·3·4 up"},
            ],
            "trouble": [
                ["서버 생성 ERROR No valid host", "compute RAM 부족 / service down", "`openstack hypervisor stats show` · `openstack compute service list`", "compute 여유 RAM 확인(실측 여유 1G 안팎), flavor 낮추기"],
                ["FIP 연결 안 됨", "OVN Gateway 에이전트", "`openstack network agent list` Alive", "해당 compute `systemctl restart ovn-controller`"],
            ],
        },
        {
            "id": "net", "name": "네트워크·라우터", "status": "live",
            "design": [
                "ext-net: flat(physnet extnet) 192.168.120.0/24, gw 192.168.120.2(s1), 풀 .200~.229.",
                "figteam-net 172.20.0.0/24 (앱망, MTU 1442, DNS 8.8.8.8). host route 10.10.2.0/24 → 172.20.0.125(rt-data 포트).",
                "data-net 10.10.2.0/24 (DB 격리망, gw 10.10.2.1).",
                "rt-edge: 앱망 ↔ ext, SNAT ON(.202), FIP 1:1 NAT. rt-data: DB망 ↔ 앱망 ↔ ext, SNAT OFF(.220) → 외부에서 10.10.2.10 이 원래 주소로 보인다.",
            ],
            "config": [
                {"label": "재현 명령 (figteam rc)", "code": r"""source /root/keystonerc_figteam
openstack network create figteam-net
openstack subnet create figteam-subnet --network figteam-net --subnet-range 172.20.0.0/24 \
  --dns-nameserver 8.8.8.8 --host-route destination=10.10.2.0/24,gateway=172.20.0.125
openstack network create data-net
openstack subnet create data-subnet --network data-net --subnet-range 10.10.2.0/24 --gateway 10.10.2.1

openstack router create rt-edge
openstack router set rt-edge --external-gateway ext-net --fixed-ip subnet=ext-subnet,ip-address=192.168.120.202
openstack router add subnet rt-edge figteam-subnet                     # 172.20.0.1

openstack router create rt-data
openstack router set rt-data --external-gateway ext-net --disable-snat \
  --fixed-ip subnet=ext-subnet,ip-address=192.168.120.220
openstack router add subnet rt-data data-subnet                        # 10.10.2.1
openstack port create rt-data-app --network figteam-net --fixed-ip ip-address=172.20.0.125
openstack router add port rt-data rt-data-app"""},
            ],
            "commands": [
                {"cat": "조회", "label": "현재 값", "code": r"""openstack network list; openstack subnet list -c Name -c Subnet -c Gateway
openstack network show figteam-net -c mtu
openstack subnet show figteam-subnet -c host_routes
openstack router show rt-edge -c external_gateway_info -c interfaces_info
openstack router show rt-data -c external_gateway_info -c interfaces_info
openstack floating ip list"""},
            ],
            "verify": [
                {"label": "라우터 외부 IP 가 s1 라우트와 일치", "code": "openstack router show rt-edge -f value -c external_gateway_info | grep -o '192.168.120.[0-9]*'", "expect": "192.168.120.202 (rt-data 는 .220)"},
            ],
            "trouble": [
                ["cp1 → db-01 불통", "host route 172.20.0.125", "cp1: `ip r | grep 10.10.2` · `openstack subnet show figteam-subnet -c host_routes`", "host route 재설정 후 VM 에서 `sudo netplan apply` 또는 DHCP 갱신"],
                ["외부에서 db-01 접속 시 출발지가 바뀜", "rt-data SNAT", "`openstack router show rt-data -c external_gateway_info` enable_snat", "rt-data 는 SNAT OFF 유지 (sg-db 가 원래 출발지로 허용)"],
            ],
        },
        {
            "id": "sg", "name": "보안그룹", "status": "live",
            "design": [
                "sg-figteam-ha(cp1·w1): 22·80·443·6443·8080·3306·30000-32767/tcp, 51820/udp, ICMP 를 0.0.0.0/0, 172.20.0.0/24 는 전부 허용.",
                "sg-db(db-01): 3306 ← 172.20.0.0/24 · 10.200.0.4/32 · 192.168.120.2/32, 22 ← 172.20.0.0/24 · 192.168.120.2, 9104(exporter) ← 172.20.0.0/24, ICMP ← 172.20.0.0/24 · 10.200.0.0/24.",
                "KT 워커 조인 시 빠진 규칙: UDP 8472(VXLAN)·TCP 10250(kubelet) ← 10.200.0.0/24, 3306 ← 10.200.0.5/32 (설계, C2·C3).",
            ],
            "config": [
                {"label": "KT 워커용 추가 규칙 (설계 · 미적용)", "code": r"""source /root/keystonerc_figteam
openstack security group rule create sg-figteam-ha --ingress --protocol udp --dst-port 8472  --remote-ip 10.200.0.0/24
openstack security group rule create sg-figteam-ha --ingress --protocol tcp --dst-port 10250 --remote-ip 10.200.0.0/24
openstack security group rule create sg-db        --ingress --protocol tcp --dst-port 3306  --remote-ip 10.200.0.5/32"""},
            ],
            "commands": [
                {"cat": "조회", "label": "규칙 확인", "code": r"""openstack security group rule list sg-figteam-ha -c 'IP Protocol' -c 'Port Range' -c 'IP Range'
openstack security group rule list sg-db -c 'IP Protocol' -c 'Port Range' -c 'IP Range'"""},
                {"cat": "적용", "label": "되돌리기", "code": "openstack security group rule delete <rule-id>"},
            ],
            "verify": [
                {"label": "KT 허브에서 포트 확인", "code": r"""# kt-edge 에서
for t in 172.20.0.86:6443 172.20.0.86:10250 10.10.2.10:3306; do
  timeout 3 bash -c "</dev/tcp/${t%:*}/${t#*:}" && echo "OK $t" || echo "FAIL $t"; done""", "expect": "실측(조인 전): 6443 OK · 10250 FAIL · 3306 FAIL"},
            ],
            "trouble": [
                ["kubectl logs/exec 가 KT 노드에서 timeout", "10250 규칙", "위 포트 확인", "sg-figteam-ha 10250 ← 10.200.0.0/24 + kt-w1 방화벽 10250"],
                ["파드 간 통신·DNS 실패(KT 노드만)", "UDP 8472", "kt-w1: `tcpdump -ni wg0 udp port 8472`", "sg-figteam-ha 8472/udp ← 10.200.0.0/24"],
            ],
        },
        {
            "id": "image", "name": "Flavor·이미지·볼륨", "status": "live",
            "design": [
                "m1.medium 2vCPU/4GB/40GB (cp1·db-01), m1.worker 2vCPU/2.5GB/20GB (w1). 이미지 Ubuntu-22.04.",
                "db-01-data 10GB Cinder 볼륨을 /var/lib/mysql 에 붙인다(VM 을 다시 만들어도 데이터 유지). vol-figteam-data 1GB 는 미사용.",
            ],
            "config": [
                {"label": "생성 명령", "code": r"""openstack flavor create m1.worker --vcpus 2 --ram 2560 --disk 20
openstack image create Ubuntu-22.04 --disk-format qcow2 --container-format bare \
  --file jammy-server-cloudimg-amd64.img --public
openstack volume create db-01-data --size 10"""},
            ],
            "commands": [
                {"cat": "조회", "label": "현재 값", "code": r"""openstack flavor list -c Name -c VCPUs -c RAM -c Disk
openstack image list
openstack volume list --all-projects -c Name -c Size -c Status"""},
            ],
            "verify": [],
            "trouble": [
                ["볼륨 attach 후 마운트 안 됨", "장치명(vdb)", "db-01: `lsblk`", "/etc/fstab 은 UUID 로: `blkid /dev/vdb`"],
            ],
        },
        {
            "id": "server", "name": "서버 생성 (재현)", "status": "live",
            "design": [
                "IP 를 고정해서 만든다 — 앱 env·sg·MySQL 계정이 IP 에 묶여 있다.",
                "배치: compute3=cp1, compute1=w1, compute4=db-01 (가용 RAM 기준).",
            ],
            "config": [
                {"label": "서버 3대", "code": r"""source /root/keystonerc_figteam
openstack server create db-01 --flavor m1.medium --image Ubuntu-22.04 --key-name s1-ktci5 \
  --nic net-id=data-net,v4-fixed-ip=10.10.2.10 --security-group sg-db
openstack server add volume db-01 db-01-data

openstack server create k8s-cp1 --flavor m1.medium --image Ubuntu-22.04 --key-name figteam-key \
  --nic net-id=figteam-net,v4-fixed-ip=172.20.0.86 --security-group sg-figteam-ha
openstack server add floating ip k8s-cp1 192.168.120.226

openstack server create k8s-w1 --flavor m1.worker --image Ubuntu-22.04 --key-name figteam-key \
  --nic net-id=figteam-net,v4-fixed-ip=172.20.0.180 --security-group sg-figteam-ha"""},
            ],
            "commands": [
                {"cat": "조회", "label": "목록·배치", "code": r"""openstack server list --all-projects -c Name -c Status -c Networks -c Flavor
openstack server show k8s-cp1 -c OS-EXT-SRV-ATTR:host -c key_name -c security_groups"""},
            ],
            "verify": [
                {"label": "3대 ACTIVE", "code": "openstack server list --all-projects -f value -c Name -c Status", "expect": "db-01 · k8s-w1 · k8s-cp1 ACTIVE"},
            ],
            "trouble": [
                ["고정 IP 충돌", "포트 잔존", "`openstack port list --fixed-ip ip-address=172.20.0.86`", "남은 포트 삭제 후 재생성"],
                ["admin rc 에서 figteam 서버 지정 실패", "프로젝트 범위", "`openstack server list --all-projects`", "이름 대신 ID 로 지정"],
            ],
        },
    ],
}

# ===================== OpenStack: k8s-cp1 =====================
PAGES["inst-cp1"] = {
    "kind": "instance",
    "cloud": "openstack",
    "title": "k8s-cp1 (k3s 서버)",
    "tag": "172.20.0.86 · FIP 192.168.120.226",
    "status": "live",
    "steps": "S8 · S12",
    "desc": "단일 k3s 서버(컨트롤 플레인 + 워크로드 가능). 플래그 없이 기본 설치라 flannel VXLAN·Traefik·ServiceLB·local-path·metrics-server 가 내장으로 돈다.",
    "specs": [
        ["OS", "Ubuntu 22.04.5 / 5.15.0-204"], ["크기", "m1.medium 2 vCPU / 3.8 GiB"],
        ["k3s", "v1.37.2+k3s1 (containerd 2.3.7)"], ["CIDR", "Pod 10.42.0.0/16 · Svc 10.43.0.0/16"],
        ["MTU", "ens3 1442 · flannel.1 1392"], ["호스트", "compute3"],
    ],
    "areas": [
        {
            "id": "k3s", "name": "k3s 서버", "status": "live",
            "design": [
                "현재 /etc/rancher/k3s/config.yaml 이 없다 → node-ip 자동(172.20.0.86), API 인증서 SAN = 172.20.0.86·k8s-cp1·10.43.0.1 뿐.",
                "그래서 외부 노드는 반드시 https://172.20.0.86:6443 으로 조인한다(FIP·KT 6443 DNAT 주소는 SAN 에 없어 TLS 실패).",
                "컨트롤 플레인은 1대(SPOF). KT 에 서버(etcd)를 두는 HA 는 2사이트·WAN 지연으로 정족수가 깨지기 쉬워 하지 않는다 → KT 는 워커로만.",
            ],
            "config": [
                {"label": "설치 (재현)", "code": r"""curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.37.2+k3s1 sh -s - server"""},
                {"label": "/etc/rancher/k3s/config.yaml 권장안 (설계 · 미적용)", "code": r"""# 적용 시 k3s 재시작 → API 수십 초 중단, 파드는 유지
node-ip: 172.20.0.86
node-external-ip: 192.168.120.226
tls-san:
  - 172.20.0.86
  - 192.168.120.226
  - k8s-cp1
node-label:
  - topology.kubernetes.io/zone=onprem"""},
            ],
            "commands": [
                {"cat": "조회", "label": "클러스터 상태", "code": r"""sudo kubectl get nodes -o wide
sudo kubectl get pods -A -o wide | grep -v Completed
sudo openssl x509 -in /var/lib/rancher/k3s/server/tls/serving-kube-apiserver.crt -noout -ext subjectAltName"""},
                {"cat": "조회", "label": "조인 토큰 위치 (값은 출력·저장하지 않음)", "code": r"""sudo test -s /var/lib/rancher/k3s/server/node-token && echo token-present
# 조인 시에만 파이프로 넘긴다:  K3S_TOKEN="$(ssh cp1 sudo cat /var/lib/rancher/k3s/server/node-token)" """},
                {"cat": "적용", "label": "config.yaml 적용 (설계안 반영 시)", "code": r"""sudo install -m 600 config.yaml /etc/rancher/k3s/config.yaml
sudo systemctl restart k3s && sudo kubectl get nodes"""},
            ],
            "verify": [
                {"label": "노드 Ready", "code": "sudo kubectl get nodes", "expect": "k8s-cp1 · k8s-w1 Ready"},
            ],
            "trouble": [
                ["`x509: certificate is valid for 172.20.0.86, not 192.168.120.226`", "K3S_URL 주소 / tls-san", "위 openssl SAN 확인", "K3S_URL=https://172.20.0.86:6443 로 조인하거나 tls-san 추가 후 재시작"],
                ["API TLS handshake timeout", "cp1 메모리", "`free -h` · `kubectl top node`", "compute3 RAM 확보(11-23 4→6GB 증설 사례)"],
                ["traefik/coredns 재시작 횟수 많음 (실측 137회·110회)", "노트북 절전·VM 일시정지", "`kubectl -n kube-system describe pod -l app.kubernetes.io/name=traefik`", "s1 절전 해제, liveness 실패 원인 확인"],
            ],
        },
        {
            "id": "cni", "name": "네트워크 (flannel·노출)", "status": "live",
            "design": [
                "flannel VXLAN(UDP 8472), VTEP = 노드 InternalIP. 사이트 밖 노드가 붙으면 그 노드 InternalIP 로 직접 VXLAN 이 나간다.",
                "cp1 → KT 방향 패킷은 FIP 1:1 NAT 로 192.168.120.226 에서 나가고, w1 은 rt-edge SNAT 로 .202 에서 나간다. KT 노드 방화벽은 이 두 주소를 허용해야 한다.",
                "Traefik LoadBalancer(svclb) 80/443 은 노드 IP 에, 앱은 NodePort 30080 으로 노출. KT Edge 경로는 VIP → FIP:30080.",
            ],
            "config": [],
            "commands": [
                {"cat": "조회", "label": "flannel·서비스", "code": r"""ip -d link show flannel.1 | grep -oE 'mtu [0-9]+|vxlan id [0-9]+|dstport [0-9]+'
sudo kubectl get node -o custom-columns=N:.metadata.name,IP:.status.addresses[0].address,VTEP:.metadata.annotations.flannel\.alpha\.coreos\.com/public-ip
sudo kubectl get svc -A | grep -E 'NodePort|LoadBalancer'
sudo kubectl -n minwon-sample get ingress"""},
            ],
            "verify": [
                {"label": "NodePort 응답", "code": "curl -sI http://127.0.0.1:30080/healthz | head -1", "expect": "200"},
            ],
            "trouble": [
                ["외부 노드 파드만 DNS 실패", "VTEP 주소(flannel public-ip)", "위 custom-columns 의 VTEP 열", "외부 노드는 `--node-ip`·`--flannel-iface` 를 WG 주소로 지정"],
                ["큰 응답만 끊김", "MTU", "`ping -M do -s 1342 <원격 파드IP>`", "C6 절차"],
            ],
        },
        {
            "id": "app", "name": "앱 배포 (minwon-sample)", "status": "live",
            "design": [
                "ArgoCD 앱 minwon-sample(Synced/Healthy)이 Deployment 를 관리한다. 직접 kubectl patch 는 다음 동기화에 덮인다 → Git 매니페스트로 바꾼다.",
                "이미지 ghcr.io/prgrmany/team6-hybrid-autorecovery-platform/minwon-app (pull secret ghcr-pull).",
                "env: SITE=onprem, DB_HOST=10.10.2.10:3306, DB_NAME=minwon_db, DB_USER=minwon, 비밀번호·CHAOS_TOKEN 은 Secret minwon-db-secret.",
                "리소스 requests 100m/128Mi, limits 500m/256Mi. 실측: 파드 2개가 모두 k8s-w1 에 있다 → w1 장애 시 전부 중단.",
                "minwon 네임스페이스는 Secret 만 남은 옛 자리(워크로드 없음).",
            ],
            "config": [
                {"label": "분산 배치 추가안 (설계 · Git 매니페스트에 반영)", "code": r"""spec:
  template:
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector: {matchLabels: {app: minwon-app}}
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone   # onprem / ktcloud
          whenUnsatisfiable: ScheduleAnyway
          labelSelector: {matchLabels: {app: minwon-app}}
      tolerations:
        - key: site
          value: ktcloud
          effect: NoSchedule"""},
            ],
            "commands": [
                {"cat": "조회", "label": "배포 상태", "code": r"""sudo kubectl -n minwon-sample get deploy,rs,pods -o wide
sudo kubectl -n minwon-sample get deploy minwon-app -o jsonpath='{.spec.template.spec.containers[0].env}'
sudo kubectl -n argocd get applications"""},
                {"cat": "적용", "label": "재시작·롤백", "code": r"""sudo kubectl -n minwon-sample rollout restart deploy/minwon-app
sudo kubectl -n minwon-sample rollout status deploy/minwon-app
sudo kubectl -n minwon-sample rollout undo deploy/minwon-app"""},
            ],
            "verify": [
                {"label": "파드 분산", "code": "sudo kubectl -n minwon-sample get pods -o wide", "expect": "NODE 열이 서로 다름 (현재 실측은 둘 다 k8s-w1)"},
            ],
            "trouble": [
                ["ImagePullBackOff", "ghcr-pull Secret / 노드 인터넷", "`kubectl -n minwon-sample describe pod <파드>`", "네임스페이스마다 ghcr-pull 필요, 노드에서 `crictl pull` 시험"],
                ["DB 접속 거부 (새 노드에서만)", "MySQL 계정 host = 172.20.0.%", "db-01: `sudo mysql -e \"select user,host from mysql.user\"`", "C3 절차 (KT 출발지 계정·sg-db)"],
                ["kubectl 수정이 되돌아감", "ArgoCD selfHeal", "`kubectl -n argocd get app minwon-sample -o yaml | grep -A3 syncPolicy`", "Git 저장소 매니페스트 수정"],
            ],
        },
        {
            "id": "hpa", "name": "HPA·PDB·metrics-server", "status": "live",
            "design": [
                "HPA minwon-app-hpa: min 2 / max 4, CPU 70% · 메모리 80%. 실측 cpu 4% · mem 33%.",
                "PDB minwon-app-pdb: minAvailable 1 → drain 때 1개는 남는다.",
                "metrics-server 는 각 kubelet :10250 을 긁는다. KT 노드가 붙으면 cp1 → kt-w1:10250 이 열려야 HPA 계산에 KT 파드가 들어간다.",
            ],
            "config": [
                {"label": "HPA (현재)", "code": r"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: {name: minwon-app-hpa, namespace: minwon-sample}
spec:
  scaleTargetRef: {apiVersion: apps/v1, kind: Deployment, name: minwon-app}
  minReplicas: 2
  maxReplicas: 4
  metrics:
    - type: Resource
      resource: {name: cpu, target: {type: Utilization, averageUtilization: 70}}
    - type: Resource
      resource: {name: memory, target: {type: Utilization, averageUtilization: 80}}"""},
            ],
            "commands": [
                {"cat": "조회", "label": "지표·스케일", "code": r"""sudo kubectl top nodes; sudo kubectl -n minwon-sample top pods
sudo kubectl -n minwon-sample get hpa,pdb
sudo kubectl -n minwon-sample describe hpa minwon-app-hpa | tail -15"""},
                {"cat": "검증", "label": "부하 시험 (스케일 아웃 확인)", "code": r"""sudo kubectl -n minwon-sample run load --rm -it --image=busybox:1.36 --restart=Never -- \
  sh -c 'while true; do wget -q -O- http://minwon-app-svc/ >/dev/null; done'
# 다른 창: watch sudo kubectl -n minwon-sample get hpa,pods -o wide"""},
            ],
            "verify": [
                {"label": "지표 수집", "code": "sudo kubectl -n minwon-sample get hpa", "expect": "TARGETS 에 <unknown> 없음"},
            ],
            "trouble": [
                ["TARGETS <unknown>", "metrics-server → kubelet 10250", "`kubectl -n kube-system logs deploy/metrics-server | tail`", "새 노드 10250 경로(SG·방화벽) 개방"],
                ["maxReplicas 에서 Pending", "노드 자원 부족", "`kubectl describe pod <Pending 파드>` Events", "KT 워커 추가(HA) 또는 버스팅(설계)"],
            ],
        },
        {
            "id": "argocd", "name": "ArgoCD·관측", "status": "live",
            "design": [
                "argocd 네임스페이스: application-controller·repo-server·redis 만 1개씩, server·dex·notifications·applicationset 은 0 (메모리 절약으로 내림). 동기화는 되지만 UI(argocd.ktci5.kr)는 꺼져 있다.",
                "kube-state-metrics NodePort 30091 — 외부 Prometheus 가 긁는 지점.",
            ],
            "config": [],
            "commands": [
                {"cat": "적용", "label": "UI 잠깐 켜기", "code": r"""sudo kubectl -n argocd scale deploy argocd-server --replicas=1
sudo kubectl -n argocd port-forward svc/argocd-server 8443:443 --address 0.0.0.0
# 끝나면: sudo kubectl -n argocd scale deploy argocd-server --replicas=0"""},
                {"cat": "조회", "label": "상태", "code": r"""sudo kubectl -n argocd get deploy,sts
curl -s http://127.0.0.1:30091/metrics | head -3"""},
            ],
            "verify": [],
            "trouble": [
                ["app OutOfSync 지속", "repo-server 재시작(실측 8회)", "`kubectl -n argocd logs deploy/argocd-repo-server | tail`", "메모리 여유 확보 후 hard refresh"],
            ],
        },
    ],
}

# ===================== OpenStack: k8s-w1 =====================
PAGES["inst-w1"] = {
    "kind": "instance",
    "cloud": "openstack",
    "title": "k8s-w1 (k3s 에이전트)",
    "tag": "172.20.0.180",
    "status": "live",
    "steps": "S8",
    "desc": "온프렘 워커. 현재 앱 파드 2개와 ArgoCD controller·repo-server 가 이 노드에 몰려 있다. FIP 가 없어 외부로 나갈 때는 rt-edge SNAT(192.168.120.202)로 보인다.",
    "specs": [
        ["OS", "Ubuntu 22.04.5"], ["크기", "m1.worker 2 vCPU / 2.4 GiB"],
        ["k3s", "v1.37.2+k3s1 agent"], ["호스트", "compute1"],
        ["접속", "figteam-key 만 (cp1 경유)"], ["외부 출발지", "192.168.120.202 (SNAT)"],
    ],
    "areas": [
        {
            "id": "agent", "name": "k3s 에이전트", "status": "live",
            "design": [
                "같은 앱망에서 조인하므로 node-ip 자동 감지로 충분하다.",
                "역할 라벨 node-role.kubernetes.io/worker 를 붙여 두었다.",
            ],
            "config": [
                {"label": "조인 (재현)", "code": r"""curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.37.2+k3s1 \
  K3S_URL=https://172.20.0.86:6443 K3S_TOKEN="<cp1 node-token>" sh -s - agent
# cp1 에서
sudo kubectl label node k8s-w1 node-role.kubernetes.io/worker=true topology.kubernetes.io/zone=onprem"""},
            ],
            "commands": [
                {"cat": "조회", "label": "에이전트 상태", "code": r"""systemctl status k3s-agent --no-pager | head -5
sudo journalctl -u k3s-agent -n 30 --no-pager
free -h"""},
                {"cat": "적용", "label": "유지보수 (drain → 복귀)", "code": r"""# cp1 에서
sudo kubectl drain k8s-w1 --ignore-daemonsets --delete-emptydir-data
sudo kubectl uncordon k8s-w1"""},
            ],
            "verify": [
                {"label": "Ready·스케줄 가능", "code": "sudo kubectl get node k8s-w1", "expect": "Ready (SchedulingDisabled 아님)"},
            ],
            "trouble": [
                ["drain 이 멈춤", "PDB minAvailable 1 + 파드가 한 노드에만", "`kubectl get pdb -A`", "다른 노드에 먼저 파드를 띄운 뒤 drain (분산 배치안 적용)"],
                ["Node password rejected", "같은 이름으로 재조인", "cp1: `kubectl -n kube-system get secret k8s-w1.node-password.k3s`", "`kubectl delete node k8s-w1` 후 Secret 삭제하고 재조인"],
            ],
        },
    ],
}

# ===================== OpenStack: db-01 =====================
PAGES["inst-db01"] = {
    "kind": "instance",
    "cloud": "openstack",
    "title": "db-01 (MySQL Primary)",
    "tag": "10.10.2.10",
    "status": "live",
    "steps": "S7",
    "desc": "온프렘 원본 DB(쓰기 권한 보유). data-net 에 격리되어 FIP 가 없고, 접속은 앱망·s1·AWS dr 만 sg-db 로 허용한다.",
    "specs": [
        ["OS", "Ubuntu 22.04.5"], ["크기", "m1.medium 2 vCPU / 3.8 GiB"],
        ["MySQL", "8.4.13 · server_id 1 · read_only 0"], ["데이터", "vdb 10G → /var/lib/mysql (Cinder db-01-data)"],
        ["복제", "GTID ON · binlog ROW · 7일 보관"], ["호스트", "compute4"],
    ],
    "areas": [
        {
            "id": "mysql", "name": "MySQL 설정·계정", "status": "live",
            "design": [
                "bind_address=10.10.2.10 — 이 주소로만 듣는다.",
                "GTID + ROW binlog 로 AWS dr 이 Auto_Position 복제(실측 지연 0초).",
                "계정: root@localhost(auth_socket), minwon@172.20.0.%(앱), 복제 계정. 앱 계정 host 가 172.20.0.% 라 다른 대역(KT 10.200.0.5)에서는 인증이 거부된다(C3).",
            ],
            "config": [
                {"label": "/etc/mysql/mysql.conf.d/ (핵심 값)", "code": r"""[mysqld]
server_id                  = 1
bind_address               = 10.10.2.10
gtid_mode                  = ON
enforce_gtid_consistency   = ON
log_bin                    = binlog
binlog_format              = ROW
binlog_expire_logs_seconds = 604800"""},
                {"label": "KT 워커용 앱 계정 (설계 · 미적용)", "code": r"""-- 비밀번호는 기존 앱 Secret 과 같은 값을 쓴다. 화면·파일에 적지 않는다.
CREATE USER 'minwon'@'10.200.0.5' IDENTIFIED BY '<minwon-db-secret 의 app-password>';
GRANT ALL ON minwon_db.* TO 'minwon'@'10.200.0.5';"""},
            ],
            "commands": [
                {"cat": "조회", "label": "상태", "code": r"""sudo mysql -e "select @@version,@@read_only,@@server_id,@@gtid_mode"
sudo mysql -e "show replicas"
sudo mysql -e "select user,host,plugin from mysql.user"
lsblk; df -h /var/lib/mysql"""},
            ],
            "verify": [
                {"label": "앱망에서 접속", "code": "# cp1 에서\ntimeout 3 bash -c '</dev/tcp/10.10.2.10/3306' && echo OK", "expect": "OK"},
            ],
            "trouble": [
                ["Access denied for user 'minwon'@'10.200.0.5'", "계정 host", "`select user,host from mysql.user`", "출발지별 계정 추가(위 설계안) — 와일드카드 % 는 쓰지 않는다"],
                ["접속 timeout (다른 대역)", "sg-db", "controller: `openstack security group rule list sg-db`", "필요한 /32 만 3306 허용"],
                ["디스크 가득", "binlog 보관 7일", "`du -sh /var/lib/mysql/binlog.*`", "`PURGE BINARY LOGS BEFORE NOW() - INTERVAL 3 DAY` (복제본 위치 확인 후)"],
            ],
        },
        {
            "id": "backup", "name": "백업", "status": "live",
            "design": [
                "15분 binlog: cron(root) */15 → /opt/minwon-backup/run-backup.sh → `FLUSH BINARY LOGS` → backup-binlog.sh(닫힌 binlog 를 /var/backups/mysql/binlog 로 복사·cmp 검증) → transfer-binlog.sh(rsync → aws-dr /var/backups/minwon/incoming/binlog) → aws-dr upload-binlog.sh(`aws s3 sync`, SSE AES256).",
                "일 1회 전체: /etc/cron.d/mysql-backup 02:30 /usr/local/sbin/mysql-backup.sh(mysqldump --single-transaction --set-gtid-purged=ON, 7일 보관) → /etc/cron.d/mysql-full-s3 03:00 transfer-full.sh → aws-dr upload-full.sh.",
                "db-01 은 인터넷 직통이 없다(실측: S3 HTTPS 000). 그래서 S3 업로드는 aws-dr 이 한다. 전송 키는 /home/ubuntu/.ssh/id_ed25519_minwon_backup.",
                "모든 단계가 flock 으로 중복 실행을 막는다.",
            ],
            "config": [
                {"label": "cron (root crontab + /etc/cron.d)", "code": r"""*/15 * * * * /bin/bash /opt/minwon-backup/run-backup.sh >> /var/log/minwon-backup.log 2>&1
30 2 * * * root /usr/local/sbin/mysql-backup.sh                                   # /etc/cron.d/mysql-backup
0 3 * * * root /bin/bash /opt/minwon-backup/transfer-full.sh >> /var/log/minwon-full-backup.log 2>&1   # /etc/cron.d/mysql-full-s3"""},
                {"label": "스크립트 연결 순서 (파일명을 누르면 실제 내용)", "code": r"""db-01  /opt/minwon-backup/run-backup.sh
        ├─ /opt/minwon-backup/backup-binlog.sh
        ├─ /opt/minwon-backup/transfer-binlog.sh   ──rsync──▶ aws-dr
        └─ ssh aws-dr upload-binlog.sh             ──S3──▶ minwon-db/binlog/
db-01  /usr/local/sbin/mysql-backup.sh  (02:30 덤프)
db-01  /opt/minwon-backup/transfer-full.sh (03:00) ──rsync──▶ aws-dr upload-full.sh ──S3──▶ minwon-db/full/"""},
            ],
            "commands": [
                {"cat": "조회", "label": "최근 백업", "code": r"""sudo crontab -l | grep -v '^#'; sudo cat /etc/cron.d/mysql-backup /etc/cron.d/mysql-full-s3
sudo tail -5 /var/log/minwon-backup.log
sudo tail -3 /var/log/minwon-full-backup.log
ls -lt /var/backups/mysql | head"""},
                {"cat": "적용", "label": "수동 실행", "code": "sudo bash /opt/minwon-backup/run-backup.sh"},
            ],
            "verify": [
                {"label": "15분 안에 두 줄", "code": "sudo tail -2 /var/log/minwon-backup.log", "expect": "'AWS Binlog 전송 완료' 와 'S3 Binlog 동기화 완료'"},
            ],
            "trouble": [
                ["전송 실패 (rsync/ssh)", "db-01 → 10.200.0.4 경로 · 백업 키", "`timeout 3 bash -c '</dev/tcp/10.200.0.4/22'` · 로그 마지막 줄", "WG(허브·dr) 핸드셰이크, rt-data → s1 → wg-kt 경로, dr authorized_keys 확인"],
                ["'ERROR: 이미 실행 중'", "flock 잠금", "`ls -l /run/lock/minwon-*.lock` · `pgrep -af minwon`", "앞 실행이 끝났는지 확인. 멈춘 rsync 가 있으면 종료"],
                ["'ERROR: 기존 백업 불일치'", "같은 이름 binlog 가 다른 내용", "`cmp /var/lib/mysql/<binlog> /var/backups/mysql/binlog/<binlog>`", "덮어쓰지 않고 멈추는 게 정상. 원인(서버 재구축 등) 확인 후 수동 정리"],
                ["S3 동기화 실패", "aws-dr 의 IAM 권한·aws CLI", "aws-dr: `aws sts get-caller-identity`", "인스턴스 역할(S3 쓰기) 확인"],
            ],
        },
    ],
}

# ===================== KT Cloud: Edge =====================
PAGES["inst-ktedge"] = {
    "kind": "instance",
    "cloud": "kt",
    "title": "kt-edge-dr-01 (인입·WAF·WG 허브)",
    "tag": "14.63.212.190 · 10.200.0.1",
    "status": "live",
    "steps": "S5 · S9",
    "desc": "공개 진입점이자 WireGuard 허브. 모든 사이트 간 트래픽이 이 1 vCPU VM 을 지난다 — 허브 장애 = 사이트 간 단절(R9 시나리오: Cloudflare → 온프렘 터널 우회).",
    "specs": [
        ["OS", "Rocky Linux 8.10 / 4.18.0-553"], ["크기", "1 vCPU / 1.7 GiB (KOR-Central A)"],
        ["사설", "eth0 172.27.0.160/16"], ["포트포워딩", "TCP 22·80·443·30080 / UDP 51820"],
        ["nginx", "1.14.1 + ModSecurity"], ["exporter", "node_exporter · wireguard_exporter"],
    ],
    "areas": [
        {
            "id": "wg", "name": "WireGuard 허브", "status": "live",
            "design": [
                "wg0 10.200.0.1/24, ListenPort 51820. peer 별 AllowedIPs 가 곧 라우팅표다(wg-quick 이 경로 자동 생성).",
                "s1 peer: 10.200.0.2/32 + 온프렘 192.168.120.0/24 · 172.20.0.0/24 · 10.10.1.0/24 · 10.10.2.0/24.",
                "aws-ctl 10.200.0.3/32, aws-dr 10.200.0.4/32(Endpoint 54.116.129.147), kt-w1 자리 10.200.0.5/32(옛 피어, 마지막 핸드셰이크 3일 전 — 키 교체 필요).",
                "net.ipv4.ip_forward=1, FORWARD ACCEPT, firewalld 꺼짐.",
            ],
            "config": [
                {"label": "/etc/wireguard/wg0.conf", "code": r"""[Interface]
Address = 10.200.0.1/24
ListenPort = 51820
PrivateKey = <허브 개인키>

[Peer]   # 온프렘 s1
PublicKey = <s1 공개키>
AllowedIPs = 10.200.0.2/32, 192.168.120.0/24, 172.20.0.0/24, 10.10.1.0/24, 10.10.2.0/24

[Peer]   # AWS ctl
PublicKey = <ctl 공개키>
AllowedIPs = 10.200.0.3/32

[Peer]   # AWS dr
PublicKey = <dr 공개키>
AllowedIPs = 10.200.0.4/32
Endpoint = 54.116.129.147:51820

[Peer]   # KT 워커 kt-w1 (새 키로 교체 예정)
PublicKey = <kt-w1 공개키>
AllowedIPs = 10.200.0.5/32"""},
            ],
            "commands": [
                {"cat": "조회", "label": "피어·경로", "code": r"""wg show wg0 | grep -E 'peer|endpoint|allowed|handshake'
ip r | grep wg0
sysctl net.ipv4.ip_forward"""},
                {"cat": "적용", "label": "피어 추가·교체 (런타임 → 파일)", "code": r"""wg set wg0 peer <kt-w1 공개키> allowed-ips 10.200.0.5/32
wg set wg0 peer <옛 공개키> remove
wg-quick save wg0          # 런타임 상태를 wg0.conf 에 저장
# syncconf 금지. 전체 재시작이 필요하면 s1 페이지의 '안전 재시작' 절차를 쓴다"""},
            ],
            "verify": [
                {"label": "온프렘·AWS 도달", "code": "ping -c3 172.20.0.86; ping -c3 10.200.0.4", "expect": "실측 RTT: 온프렘 avg 29ms(9~66, Wi-Fi 지터) · AWS 5ms"},
            ],
            "trouble": [
                ["peer 핸드셰이크 없음", "피어 공개키 / 상대 Endpoint", "`wg show wg0 latest-handshakes`", "NAT 뒤 피어는 상대가 keepalive 로 먼저 붙어야 함"],
                ["허브는 되는데 온프렘만 불통", "s1 peer AllowedIPs", "`ip r get 172.20.0.86`", "온프렘 대역이 s1 peer 에만 있는지 확인"],
            ],
        },
        {
            "id": "nginx", "name": "nginx Edge·WAF", "status": "live",
            "design": [
                "edge-http/https(:80/:443, server_name minwon.ktci5.kr origin-kt.ktci5.kr) → 127.0.0.1:8081(minwon.conf, ModSecurity on) → upstream minwon_backend.",
                "레이트리밋 edge_per_ip 20r/s burst 40, 초과 429.",
                "upstream.conf 는 Ansible switch_edge.yml 이 모드(onprem/aws)에 따라 다시 쓴다 → 손으로 고치면 다음 전환 때 사라진다. 템플릿을 고친다.",
                "edge-status :8088 은 WG 전용 상태 화면(kt-edge.ktci5.kr).",
            ],
            "config": [
                {"label": "/etc/nginx/conf.d/upstream.conf (현재 · mode onprem)", "code": r"""# Managed by Ansible Recovery (switch_edge.yml)
upstream minwon_backend {
    server 10.10.1.100:80 max_fails=3 fail_timeout=10s;
    keepalive 32;
}"""},
                {"label": "KT 워커 추가안 (설계 · switch_edge.yml 템플릿에 반영)", "code": r"""upstream minwon_backend {
    server 10.10.1.100:80  max_fails=3 fail_timeout=10s;   # 온프렘 VIP
    server 10.200.0.5:30081 max_fails=3 fail_timeout=10s;  # kt-w1 전용 NodePort (Local)
    keepalive 32;
}"""},
            ],
            "commands": [
                {"cat": "조회", "label": "설정·로그", "code": r"""nginx -T 2>/dev/null | grep -E 'listen|server_name|proxy_pass|upstream|server ' | head -30
tail -f /var/log/nginx/access.log"""},
                {"cat": "적용", "label": "반영", "code": "nginx -t && systemctl reload nginx"},
            ],
            "verify": [
                {"label": "엣지 → 백엔드", "code": r"""curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: minwon.ktci5.kr' http://127.0.0.1/
curl -sI http://10.10.1.100/healthz | head -1""", "expect": "200 / 200"},
            ],
            "trouble": [
                ["502 Bad Gateway", "upstream 대상", "`curl -sI http://10.10.1.100/healthz`", "s1 VIP DNAT·NodePort 순서로 점검"],
                ["정상 요청 403", "ModSecurity 룰", "`grep -i modsec /var/log/nginx/error.log | tail`", "/opt/waf-staging 룰 예외 처리"],
                ["upstream 수정이 사라짐", "switch_edge.yml", "파일 첫 줄 'Managed by Ansible'", "Ansible 템플릿 수정"],
            ],
        },
        {
            "id": "nat", "name": "iptables (6443 DNAT)", "status": "live",
            "design": [
                "PREROUTING tcp 6443 → 192.168.120.226:6443 DNAT + MASQUERADE 가 걸려 있다(옛 KT 워커 조인용).",
                "인터페이스 조건(-i wg0)이 없어 KT 포트포워딩에 6443 이 추가되면 바로 공개된다. 현재 포워딩 목록에는 없음.",
                "새 설계는 kt-w1 이 172.20.0.86:6443 으로 직접 조인 → 이 DNAT 는 필요 없다. 정리 대상.",
            ],
            "config": [],
            "commands": [
                {"cat": "조회", "label": "NAT 규칙", "code": "iptables -t nat -S | grep -E '6443|DNAT|MASQ'"},
                {"cat": "적용", "label": "정리 (설계 · 확인 후)", "code": r"""iptables -t nat -D PREROUTING -p tcp --dport 6443 -j DNAT --to-destination 192.168.120.226:6443
iptables -t nat -D POSTROUTING -d 192.168.120.226/32 -p tcp --dport 6443 -j MASQUERADE"""},
            ],
            "verify": [],
            "trouble": [
                ["외부에서 6443 응답", "KT 포트포워딩 + 조건 없는 DNAT", "KT 콘솔 포트포워딩 목록", "DNAT 삭제 또는 `-i wg0` 조건 추가"],
            ],
        },
    ],
}

# ===================== KT Cloud: kt-w1 (설계) =====================
PAGES["inst-ktw1"] = {
    "kind": "instance",
    "cloud": "kt",
    "title": "kt-w1 (KT 워커 조인 · 설계)",
    "tag": "WG 10.200.0.5",
    "status": "design",
    "steps": "S12 (S1~S11 통과 후)",
    "desc": "KT Cloud VM 을 온프렘 k3s 에 워커로 붙인다. 아래 탭 순서대로 진행하면 조인 단계에서 막히지 않도록 실측으로 찾은 제약(C1~C12)을 먼저 없앤다. 전 과정은 '설계'이며 적용 전 영향 범위를 확인한다.",
    "specs": [
        ["권장 OS", "Ubuntu 22.04 (cgroup v2)"], ["권장 크기", "2 vCPU / 4 GB"],
        ["연결", "개별 WG peer → KT 허브"], ["node-ip", "10.200.0.5 (flannel-iface wg0)"],
        ["라벨/taint", "zone=ktcloud · site=ktcloud:NoSchedule"], ["k3s", "v1.37.2+k3s1 agent"],
    ],
    "areas": [
        {
            "id": "pre", "name": "① 사전 점검", "status": "design",
            "design": [
                "왜 개별 WG peer 인가: KT 사설망(172.27/16)으로 허브에 붙여 라우팅하면 KT SDN 의 출발지 검사에 막힐 수 있다. WG 로 감싸면 KT 망은 UDP 51820 만 본다.",
                "옛 KT 워커(k8s-w2) 흔적: 허브의 10.200.0.5 peer 키, KT 허브 6443 DNAT. 새 키로 교체하고 DNAT 는 쓰지 않는다.",
            ],
            "config": [
                {"label": "/root/kt-w1-preflight.sh (kt-w1 에서 실행)", "code": r"""#!/bin/bash
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
exit $FAIL"""},
            ],
            "commands": [
                {"cat": "검증", "label": "실행", "code": "sudo bash /root/kt-w1-preflight.sh"},
            ],
            "verify": [
                {"label": "모든 항목 OK", "code": "sudo bash /root/kt-w1-preflight.sh; echo exit=$?", "expect": "exit=0 일 때만 ④ 조인"},
            ],
            "trouble": [
                ["tcp 10.10.2.10:3306 FAIL", "sg-db · MySQL 계정", "controller sg-db 규칙", "② 의 C3 적용"],
                ["MTU FAIL", "터널 중첩", "`ping -M do -s <크기>` 로 최대값 찾기", "C6"],
            ],
        },
        {
            "id": "wg", "name": "② WG·OpenStack 개방", "status": "design",
            "design": [
                "kt-w1 wg0: 허브 하나만 peer, AllowedIPs 에 온프렘 3대역 + WG 대역. 허브는 10.200.0.5/32 를 이미 갖고 있어 키만 바꾸면 된다.",
                "s1 wg-kt AllowedIPs 10.200.0.0/24 에 .5 가 포함 → s1 수정 불필요.",
                "OpenStack: sg-figteam-ha 에 8472/udp·10250/tcp, sg-db 에 3306 (출발지 10.200.0.5).",
                "kt-w1 자체 방화벽: VXLAN·kubelet 은 192.168.120.226(cp1 FIP NAT)·192.168.120.202(w1 SNAT)·172.20.0.0/24 에서 들어온다.",
            ],
            "config": [
                {"label": "kt-w1 /etc/wireguard/wg0.conf", "code": r"""[Interface]
Address = 10.200.0.5/24
PrivateKey = <kt-w1 개인키: wg genkey 로 이 VM 에서만 생성>

[Peer]   # KT 허브
PublicKey = <허브 공개키>
Endpoint = 172.27.0.160:51820        # 같은 KT 망이면 사설, 다른 존이면 14.63.212.190
AllowedIPs = 10.200.0.0/24, 172.20.0.0/24, 192.168.120.0/24, 10.10.2.0/24, 10.10.1.0/24
PersistentKeepalive = 25"""},
                {"label": "kt-w1 방화벽 (ufw 예시)", "code": r"""ufw allow in on wg0 from 192.168.120.0/24
ufw allow in on wg0 from 172.20.0.0/24
ufw allow in on wg0 from 10.200.0.0/24
ufw allow 22/tcp"""},
            ],
            "commands": [
                {"cat": "설치", "label": "kt-w1 WG 기동", "code": r"""sudo apt-get install -y wireguard
wg genkey | sudo tee /etc/wireguard/kt-w1.key | wg pubkey     # 공개키만 허브에 전달
sudo chmod 600 /etc/wireguard/kt-w1.key
sudo systemctl enable --now wg-quick@wg0"""},
                {"cat": "적용", "label": "허브 키 교체 (KT 허브에서)", "code": r"""wg set wg0 peer <옛 k8s-w2 공개키> remove
wg set wg0 peer <kt-w1 공개키> allowed-ips 10.200.0.5/32
wg-quick save wg0"""},
                {"cat": "적용", "label": "OpenStack 규칙 (controller)", "code": r"""source /root/keystonerc_figteam
openstack security group rule create sg-figteam-ha --ingress --protocol udp --dst-port 8472  --remote-ip 10.200.0.0/24
openstack security group rule create sg-figteam-ha --ingress --protocol tcp --dst-port 10250 --remote-ip 10.200.0.0/24
openstack security group rule create sg-db        --ingress --protocol tcp --dst-port 3306  --remote-ip 10.200.0.5/32"""},
            ],
            "verify": [
                {"label": "양방향", "code": r"""# kt-w1: ping -c2 172.20.0.86 ; ping -c2 172.20.0.180
# cp1  : ping -c2 10.200.0.5""", "expect": "양쪽 응답"},
            ],
            "trouble": [
                ["cp1 → 10.200.0.5 불통", "허브 peer / kt-w1 AllowedIPs 에 192.168.120.0/24 누락", "kt-w1: `tcpdump -ni wg0 icmp`", "cp1 패킷은 192.168.120.226 출발지로 온다 → AllowedIPs 에 포함"],
            ],
        },
        {
            "id": "join", "name": "③ k3s 에이전트 조인", "status": "design",
            "design": [
                "K3S_URL 은 SAN 에 있는 https://172.20.0.86:6443 만 쓴다.",
                "--node-ip / --flannel-iface 를 WG 로 고정: 지정하지 않으면 eth0(172.27.x)를 광고해 온프렘이 VXLAN 을 보낼 곳이 없다 → 파드는 Running 인데 DNS·서비스가 안 됨.",
                "처음에는 taint 로 막아 두고(site=ktcloud:NoSchedule) 검증 후 앱만 toleration 으로 올린다.",
            ],
            "config": [
                {"label": "/etc/rancher/k3s/config.yaml (kt-w1)", "code": r"""node-ip: 10.200.0.5
flannel-iface: wg0
node-label:
  - topology.kubernetes.io/zone=ktcloud
  - site=ktcloud
node-taint:
  - site=ktcloud:NoSchedule
# Rocky 8 등 cgroup v1 이미지일 때만:
# kubelet-arg:
#   - "fail-cgroupv1=false" """},
            ],
            "commands": [
                {"cat": "설치", "label": "조인 (토큰은 파이프로만)", "code": r"""# 맥에서 한 줄 — 토큰이 화면·파일에 남지 않는다
TOKEN="$(ssh cp1 sudo cat /var/lib/rancher/k3s/server/node-token)"
ssh kt-w1 "curl -sfL https://get.k3s.io | sudo INSTALL_K3S_VERSION=v1.37.2+k3s1 \
  K3S_URL=https://172.20.0.86:6443 K3S_TOKEN='$TOKEN' sh -s - agent"
unset TOKEN"""},
                {"cat": "조회", "label": "조인 확인 (cp1)", "code": r"""sudo kubectl get nodes -o wide
sudo kubectl get node kt-w1 -o jsonpath='{.metadata.annotations.flannel\.alpha\.coreos\.com/public-ip}'"""},
                {"cat": "적용", "label": "롤백", "code": r"""sudo kubectl drain kt-w1 --ignore-daemonsets --delete-emptydir-data
sudo kubectl delete node kt-w1
ssh kt-w1 sudo /usr/local/bin/k3s-agent-uninstall.sh"""},
            ],
            "verify": [
                {"label": "파드 네트워크", "code": r"""sudo kubectl run net-kt --rm -it --image=busybox:1.36 --restart=Never \
  --overrides='{"spec":{"nodeName":"kt-w1","tolerations":[{"operator":"Exists"}]}}' -- \
  sh -c 'nslookup minwon-app-svc.minwon-sample && wget -qO- http://minwon-app-svc.minwon-sample/healthz'""", "expect": "DNS 응답 + healthz"},
            ],
            "trouble": [
                ["x509 certificate is valid for 172.20.0.86", "K3S_URL", "조인 명령의 주소", "172.20.0.86 으로 다시"],
                ["Node password rejected", "같은 이름 재조인", "`kubectl -n kube-system get secret kt-w1.node-password.k3s`", "노드·Secret 삭제 후 재조인"],
                ["NotReady + cgroup 오류", "cgroup v1 OS", "`journalctl -u k3s-agent | grep -i cgroup`", "kubelet-arg fail-cgroupv1=false 또는 Ubuntu 22.04"],
                ["Ready 인데 파드 DNS 실패", "VTEP=172.27.x / UDP 8472", "위 public-ip 주석 값", "node-ip·flannel-iface=wg0, sg 8472"],
            ],
        },
        {
            "id": "ha", "name": "④ 배치 (HA)", "status": "design",
            "design": [
                "앱 Deployment 에 toleration + zone 분산(topologySpreadConstraints)을 넣어 온프렘 1 · KT 1 로 나눈다. ArgoCD 가 관리하므로 Git 매니페스트에 넣는다.",
                "KT Edge 가 kt-w1 파드로 바로 보내도록 전용 Service(NodePort 30081, externalTrafficPolicy: Local)를 따로 만든다.",
                "기존 minwon-app-svc 는 Cluster 그대로 둔다 — Local 로 바꾸면 파드가 없는 cp1:30080(VIP 경로)이 끊긴다(실측상 파드가 모두 w1).",
                "KT 파드의 DB 질의는 WG 왕복(실측 avg 29~56ms)을 탄다 → 질의 수 많은 화면은 지연이 커진다. 읽기 위주부터 분산.",
            ],
            "config": [
                {"label": "minwon-app-kt Service (설계)", "code": r"""apiVersion: v1
kind: Service
metadata: {name: minwon-app-kt, namespace: minwon-sample}
spec:
  type: NodePort
  externalTrafficPolicy: Local      # kt-w1 에 있는 파드만 응답
  selector: {app: minwon-app}
  ports:
    - port: 80
      targetPort: 8080              # 컨테이너 포트는 minwon-app-svc 의 targetPort 와 맞춘다
      nodePort: 30081"""},
            ],
            "commands": [
                {"cat": "조회", "label": "targetPort 확인", "code": "sudo kubectl -n minwon-sample get svc minwon-app-svc -o jsonpath='{.spec.ports[0].targetPort}'"},
                {"cat": "검증", "label": "KT 경로", "code": r"""# KT 허브에서
curl -sI http://10.200.0.5:30081/healthz | head -1"""},
            ],
            "verify": [
                {"label": "사이트 분산", "code": "sudo kubectl -n minwon-sample get pods -o wide", "expect": "kt-w1 1개 + 온프렘 1개"},
            ],
            "trouble": [
                ["KT 파드만 DB 오류", "C3 (계정·sg-db)", "파드 로그", "db-01 계정 minwon@10.200.0.5 + sg-db"],
                ["30081 응답 없음", "Local 정책 + 파드 없음", "`kubectl get pods -o wide`", "kt-w1 에 파드가 떠야 응답"],
            ],
        },
        {
            "id": "hpa", "name": "⑤ HPA·버스팅", "status": "design",
            "design": [
                "HPA(2~4)는 그대로 쓰고, 분산 규칙 덕분에 늘어난 파드가 KT 쪽에도 놓인다. metrics-server → kt-w1:10250 이 열려 있어야 계산된다.",
                "노드 단위 확장(버스팅): KT Cloud 는 Cluster Autoscaler 를 지원하지 않는다 → Pending 2분 지속 시 ktcloud-api 로 VM 생성 + cloud-init 조인 스크립트, 부하 해소 시 drain·삭제.",
                "컨트롤 플레인 HA 는 하지 않는다(2사이트 정족수 문제). 대신 cp1 장애 시 기존 파드·Edge 경로는 유지되고 AWS DR 이 최종 대비.",
            ],
            "config": [
                {"label": "버스팅 판정 (설계 · cp1 cron)", "code": r"""PENDING=$(kubectl -n minwon-sample get pods --field-selector=status.phase=Pending \
  -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}{"\n"}{end}' | wc -l)
[ "$PENDING" -gt 0 ] && echo "버스팅 필요: KT VM 생성 → cloud-init 으로 ③ 조인"
# 생성은 맥 ktcloud-api: python3 ktc.py d POST server/servers --json kt-wN.json --apply"""},
            ],
            "commands": [
                {"cat": "검증", "label": "스케일 아웃 시험", "code": "watch sudo kubectl -n minwon-sample get hpa,pods -o wide"},
            ],
            "verify": [
                {"label": "부하 시 4개까지", "code": "sudo kubectl -n minwon-sample get hpa", "expect": "REPLICAS 2→4, KT 노드에 배치"},
            ],
            "trouble": [
                ["ktc.py 401 (실측)", "키체인 API 키 만료", "`python3 ktc.py secret --help`", "KT 콘솔에서 키 재발급 후 키체인 저장"],
            ],
        },
    ],
}

# ===================== AWS: dr =====================
PAGES["inst-awsdr"] = {
    "kind": "instance",
    "cloud": "aws",
    "title": "aws-dr (Pilot-Light)",
    "tag": "10.200.0.4 · 10.51.1.165",
    "status": "live",
    "steps": "S5 · S10",
    "desc": "평시 읽기 전용 대기. 단일 노드 k3s 에 앱 1개와 MySQL 복제본(StatefulSet)을 둔다. 승격 스크립트는 펜싱 검증이 붙기 전까지 막혀 있다(fail-closed). db-01 백업을 받아 S3 로 올리는 중계 역할도 한다.",
    "specs": [
        ["EC2", "t3.small · Rocky 8.10 · 30GB"], ["RAM", "1.7 GiB (+swap 2G)"],
        ["VPC", "10.51.0.0/16 · 공인 54.116.129.147"], ["k3s", "v1.37.2+k3s1 (cgroup v1)"],
        ["MySQL", "8.4.13 · server_id 2 · read_only 1"], ["SSH", "s1 경유만 (minwon-key.pem, rocky)"],
    ],
    "areas": [
        {
            "id": "wg", "name": "네트워크·WG", "status": "live",
            "design": [
                "wg0 10.200.0.4/24 → KT 허브. AllowedIPs 10.200.0.0/24 · 192.168.120.0/24 · 10.10.1.0/24 · 10.10.2.0/24.",
                "보안그룹 22 는 admin_cidrs 만 → 집·KT 공인에서도 막힘, s1 WG 경유로만 들어간다.",
            ],
            "config": [
                {"label": "/etc/wireguard/wg0.conf", "code": r"""[Interface]
Address = 10.200.0.4/24
ListenPort = 51820
PrivateKey = <dr 개인키>

[Peer]   # KT 허브
PublicKey = <허브 공개키>
Endpoint = 14.63.212.190:51820
AllowedIPs = 10.200.0.0/24, 192.168.120.0/24, 10.10.1.0/24, 10.10.2.0/24
PersistentKeepalive = 25"""},
            ],
            "commands": [
                {"cat": "조회", "label": "상태", "code": r"""sudo wg show wg0 | grep -E 'endpoint|allowed|handshake'
ping -c2 10.10.2.10"""},
            ],
            "verify": [],
            "trouble": [
                ["SSH 타임아웃", "admin_cidrs", "맥에서 `ssh -J s1 rocky@10.200.0.4`", "공인 22 로 접속하지 않는다"],
            ],
        },
        {
            "id": "k3s", "name": "k3s (단일 노드)", "status": "live",
            "design": [
                "Rocky 8 = cgroup v1 → `fail-cgroupv1=false` 없으면 kubelet 이 뜨지 않는다.",
                "minwon-dr 네임스페이스: minwon-app 1/1(NodePort 30080), minwon-mysql StatefulSet 1/1.",
                "온프렘 클러스터와 별개(조인하지 않음) — DR 사이트는 독립이어야 한다.",
            ],
            "config": [
                {"label": "/etc/rancher/k3s/config.yaml", "code": r"""kubelet-arg:
  - "fail-cgroupv1=false" """},
            ],
            "commands": [
                {"cat": "조회", "label": "워크로드 (sudo PATH 에 k3s 없음 → 절대경로)", "code": r"""K=/usr/local/bin/k3s
sudo $K kubectl get nodes -o wide
sudo $K kubectl -n minwon-dr get deploy,sts,svc,pods"""},
            ],
            "verify": [
                {"label": "앱 대기 응답", "code": "curl -sI http://10.200.0.4:30080/healthz | head -1", "expect": "200"},
            ],
            "trouble": [
                ["`sudo: k3s: 명령이 없습니다` (실측)", "sudo secure_path", "`which k3s`", "/usr/local/bin/k3s 절대경로"],
                ["메모리 부족·OOM", "1.7GiB", "`free -h` · `dmesg | grep -i oom`", "앱 replicas 1 유지, swap 확인"],
            ],
        },
        {
            "id": "mysql", "name": "MySQL 복제·역터널", "status": "live",
            "design": [
                "minwon-mysql-0 이 db-01(10.10.2.10:3306)에서 GTID Auto_Position 복제. 실측 IO/SQL Yes, 지연 0초, read_only=1.",
                "minwon-mysql-tunnel.service: `k3s kubectl port-forward --address 10.200.0.4 svc/minwon-mysql 13306:3306` — failback 때 db-01 이 dr 을 원본으로 복제받는 통로.",
                "/opt/minwon-dr 스크립트는 **안전하게 실패(fail-closed)** 하도록 만들어져 있다(실측): /opt/minwon-dr/promote-mysql.sh 와 /opt/minwon-dr/check-fencing.sh 는 온프렘 쓰기 차단(펜싱)을 독립적으로 검증하는 장치가 붙기 전까지 BLOCKED 를 출력하고 exit 1.",
                "그래서 /opt/minwon-dr/preflight.sh <최종 GTID> 는 validate-replica.sh → check-gtid.sh 를 통과해도 마지막 check-fencing.sh 에서 반드시 멈춘다. 현재 자동 승격은 불가 — 의도된 상태.",
                "prepare-reverse-replication.sh 는 failback-precheck.sh 만 돌리고 '역방향 복제 자동 실행은 아직 미구현' 으로 exit 2.",
            ],
            "config": [
                {"label": "/opt/minwon-dr/mysql-reverse-tunnel.sh", "code": r"""set -euo pipefail
exec /usr/local/bin/k3s kubectl port-forward --address 10.200.0.4 -n minwon-dr svc/minwon-mysql 13306:3306"""},
            ],
            "commands": [
                {"cat": "조회", "label": "복제 상태", "code": r"""sudo /usr/local/bin/k3s kubectl -n minwon-dr exec minwon-mysql-0 -- \
  sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "show replica status\G"' 2>/dev/null \
  | grep -E 'Source_Host|Replica_IO_Running|Replica_SQL_Running:|Seconds_Behind|Last_.*Error:'
sudo bash /opt/minwon-dr/check-replica.sh      # 읽기만 함 (DB 변경 없음)"""},
                {"cat": "검증", "label": "승격 사전 점검 (현재는 펜싱 단계에서 BLOCKED 가 정상)", "code": r"""# 최종 GTID 는 db-01 에서: sudo mysql -N -e "select @@gtid_executed"
sudo bash /opt/minwon-dr/preflight.sh '<db-01 최종 GTID>'
#  → validate-replica.sh PASS → check-gtid.sh PASS → check-fencing.sh BLOCKED (exit 1)
sudo bash /opt/minwon-dr/failback-precheck.sh   # 되돌림 전 상태·온프렘 3306 도달"""},
            ],
            "verify": [
                {"label": "평시 기준", "code": "sudo bash /opt/minwon-dr/validate-replica.sh", "expect": "PASS: Replica 복제 상태 정상"},
            ],
            "trouble": [
                ["Replica_IO_Running: Connecting", "db-01 3306 경로 / sg-db 10.200.0.4", "`timeout 3 bash -c '</dev/tcp/10.10.2.10/3306'`", "sg-db·허브 AllowedIPs(10.10.2.0/24) 확인"],
                ["GTID 오류 1236", "binlog 만료(7일)", "Last_IO_Error", "백업에서 재시드"],
                ["역터널 서비스 반복 재시작", "API·파드 미준비", "`journalctl -u minwon-mysql-tunnel -n 30`", "minwon-mysql-0 Ready 확인"],
                ["promote-mysql.sh 가 BLOCKED", "펜싱 검증기 미연동 (의도된 상태)", "/opt/minwon-dr/check-fencing.sh 내용", "자동 승격은 막혀 있음. 승격은 온프렘 쓰기 차단을 사람이 확인한 뒤 수동 절차로만"],
            ],
        },
    ],
}

# ===================== AWS: ctl =====================
PAGES["inst-awsctl"] = {
    "kind": "instance",
    "cloud": "aws",
    "title": "aws-ctl (Recovery Orchestrator)",
    "tag": "10.200.0.3 · 10.50.1.85",
    "status": "nolook",
    "steps": "S5 · S10",
    "desc": "관제·복구 판정. 내부(SSH)는 키 불일치로 실측하지 못했고, WG 너머 HTTP API 로만 확인했다. FastAPI '민원불패 Recovery Orchestrator 0.1.0' 이 :8080 에서 응답한다.",
    "specs": [
        ["EC2", "t3.small · Rocky 8 · 20GB (노션)"], ["VPC", "10.50.0.0/16"],
        ["공인 IP", "노션 13.125.163.58 / 허브 실측 13.124.253.30"], ["API", ":8080 FastAPI"],
        ["공개", "aws-ctl.ktci5.kr (Cloudflare Tunnel)"], ["SSH", "실측 실패 (publickey)"],
    ],
    "areas": [
        {
            "id": "api", "name": "Orchestrator API", "status": "live",
            "design": [
                "엔드포인트(openapi 실측): /healthz · /metrics · /alerts · /incidents · /serving · /failback · /report/{incidents,risk,levels,steps,summary}.",
                "S1(앱)·S2(DB 복제)·S3(네트워크) 신호로 L1 파드 재시작 → L2 Ansible 복구 → L3 Edge 절체를 판정한다(설계 문서 기준).",
            ],
            "config": [],
            "commands": [
                {"cat": "조회", "label": "s1 에서 API 확인", "code": r"""curl -s http://10.200.0.3:8080/healthz
curl -s http://10.200.0.3:8080/serving
curl -s http://10.200.0.3:8080/report/summary | head -c 600
curl -s http://10.200.0.3:8080/openapi.json | python3 -c 'import sys,json; print(list(json.load(sys.stdin)["paths"]))'"""},
            ],
            "verify": [
                {"label": "헬스", "code": "curl -s -o /dev/null -w '%{http_code}\\n' http://10.200.0.3:8080/healthz", "expect": "200"},
            ],
            "trouble": [
                ["SSH publickey 거부 (실측)", "키페어 / 인스턴스 재생성", "허브 Endpoint 13.124.253.30 ≠ 노션 13.125.163.58", "EIP 고정 여부·키페어 이름 확인, SSM Session Manager 로 접속(`aws ssm start-session`)"],
                ["aws-ctl.ktci5.kr 502", "WG ctl peer", "KT: `wg show wg0` ctl handshake", "ctl wg-quick 재시작(SSM)"],
            ],
        },
    ],
}

# ===================== 확장 설계: KT 조인 제약 매트릭스 =====================
PAGES["design-kt"] = {
    "kind": "doc",
    "title": "KT 확장 설계 — HA / HPA 와 제약 제거",
    "tag": "설계",
    "desc": "온프렘 k3s 에 KT Cloud 를 붙이는 방식 비교와, 실측으로 찾은 연결 단계 제약 12개. 모든 항목이 '해소'가 되어야 조인 단계에서 막히지 않는다.",
    "blocks": [
        {"type": "h", "text": "방식 비교"},
        {"type": "table", "head": ["방식", "무엇이 늘어나나", "장점", "한계", "판단"], "rows": [
            ["HA — KT 워커 상시 조인", "노드(kt-w1)", "사이트 분산: w1·compute1 장애에도 KT 파드가 응답", "WG 경유 DB 지연 29~56ms, 허브 SPOF", "1단계 권장"],
            ["HPA — 파드 자동 확장", "파드(2→4)", "이미 구성됨, 분산 규칙만 추가", "노드 자원이 없으면 Pending", "HA 와 함께"],
            ["노드 버스팅", "KT VM(kt-w2..n)", "피크 때만 비용", "Cluster Autoscaler 미지원 → 스크립트", "2단계(시간 남으면)"],
            ["컨트롤 플레인 HA", "k3s 서버(etcd)", "API SPOF 제거", "2사이트 정족수·WAN 지연으로 오히려 위험", "하지 않음"],
        ]},
        {"type": "h", "text": "연결 단계 제약 매트릭스 (실측 " + MEASURED + ")"},
        {"type": "table", "head": ["#", "제약", "실측", "조치", "확인 명령"], "rows": [
            ["C1", "KT ↔ 172.20.0.0/24 라우팅", "해소됨: 허브→cp1:6443·w1:30080 OK, cp1→허브 OK", "kt-w1 AllowedIPs 에 온프렘 대역 포함", "kt-w1: `ping 172.20.0.86`"],
            ["C2", "SG 에 VXLAN 8472·kubelet 10250 없음", "10250 FAIL", "sg-figteam-ha 규칙 2개 추가", "허브: `</dev/tcp/172.20.0.86/10250`"],
            ["C3", "DB: sg-db 와 MySQL 계정 host", "3306 FAIL, 계정 minwon@172.20.0.%", "sg-db 10.200.0.5/32 + 계정 minwon@10.200.0.5", "`select user,host from mysql.user`"],
            ["C4", "API 인증서 SAN", "SAN = 172.20.0.86 만", "K3S_URL=https://172.20.0.86:6443 (또는 tls-san 추가·재시작)", "openssl x509 -ext subjectAltName"],
            ["C5", "노드 IP / VTEP", "미지정 시 172.27.x 광고", "--node-ip 10.200.0.5 --flannel-iface wg0", "flannel public-ip 주석"],
            ["C6", "MTU 중첩", "경로 1420 DF 통과, cp1 flannel 1392 → 외부 VXLAN 1442", "VXLAN 외부 패킷은 DF 없음 → s1 에서 단편화(동작). 성능 문제 시 cp1·w1 ens3 MTU 1420 고정 후 k3s 재시작", "`ping -M do -s 1342`"],
            ["C7", "버전", "v1.37.2+k3s1", "INSTALL_K3S_VERSION 고정", "`k3s --version`"],
            ["C8", "cgroup", "Rocky 8 = v1 (aws-dr 선례)", "Ubuntu 22.04 또는 fail-cgroupv1=false", "`stat -fc %T /sys/fs/cgroup`"],
            ["C9", "옛 조인 잔재", "허브 10.200.0.5 옛 키(3일 무응답), 허브 6443 DNAT", "키 교체, DNAT 정리", "`wg show` · `iptables -t nat -S`"],
            ["C10", "노드 이름·비밀번호", "cp1·w1 Secret 만 존재", "새 이름 kt-w1, 재조인 시 Secret 삭제", "`kubectl -n kube-system get secret | grep node-password`"],
            ["C11", "Edge upstream 관리 주체", "switch_edge.yml 이 덮어씀", "템플릿에 kt-w1:30081 추가", "upstream.conf 첫 줄"],
            ["C12", "Service 정책", "파드 2개 모두 w1", "기존 svc 유지, KT 전용 NodePort 30081 Local", "`kubectl get pods -o wide`"],
        ]},
        {"type": "h", "text": "진행 순서 (KT 확장만)"},
        {"type": "code", "label": "체크리스트", "code": r"""[ ] 1. KT 콘솔: kt-w1 생성 (Ubuntu 22.04, 2vCPU/4GB), 키페어 edgekey
[ ] 2. kt-w1: WireGuard 키 생성 → 허브 peer 교체 (C9)          … KT 허브
[ ] 3. controller: sg-figteam-ha 8472/10250, sg-db 3306 (C2·C3)  … OpenStack
[ ] 4. db-01: minwon@10.200.0.5 계정 (C3)                        … MySQL
[ ] 5. kt-w1: preflight.sh exit=0 (C1·C5·C6·C8)
[ ] 6. kt-w1: config.yaml + 조인 (C4·C7·C10), taint 유지
[ ] 7. cp1: busybox 로 kt-w1 파드 DNS·서비스 확인
[ ] 8. Git: toleration + zone 분산 + minwon-app-kt(30081) (C12)   … ArgoCD
[ ] 9. switch_edge.yml 템플릿에 10.200.0.5:30081 (C11)            … KT Edge
[ ] 10. HPA 부하 시험, 장애 시험(w1 drain → KT 단독 응답)"""},
    ],
}

# ===================== 오류 대응 색인 =====================
PAGES["trouble"] = {
    "kind": "doc",
    "title": "변수별 오류 확인 색인",
    "tag": "어디를 볼까",
    "desc": "값(변수)이 바뀌어 오류가 나면 그 값을 쓰는 곳을 모두 고쳐야 한다. 아래는 각 인스턴스 페이지의 '오류 시 확인' 표를 모은 것이다.",
    "blocks": [{"type": "troubleall"}],
}

# ---------------------------------------------------------------------------
NAV = [
    {"title": "시작하기", "items": [
        ["overview", "전체 구성·변수표", "경로도 · 변수 19개"],
        ["steps", "선행 항목과 순서", "S0 → S12 통과 조건"],
    ]},
    {"title": "온프렘 호스트", "cloud": "onprem", "items": [
        ["inst-s1", "s1 (t1-vm2)", "10.10.10.8 · VMware·NAT·WG"],
    ]},
    {"title": "OpenStack", "cloud": "openstack", "items": [
        ["inst-controller", "controller (+compute)", "192.168.120.160"],
        ["inst-cp1", "k8s-cp1", "172.20.0.86 · k3s 서버"],
        ["inst-w1", "k8s-w1", "172.20.0.180 · 워커"],
        ["inst-db01", "db-01", "10.10.2.10 · MySQL"],
    ]},
    {"title": "KT Cloud", "cloud": "kt", "items": [
        ["inst-ktedge", "kt-edge-dr-01", "14.63.212.190 · 허브"],
        ["inst-ktw1", "kt-w1 (설계)", "10.200.0.5 · 조인"],
    ]},
    {"title": "AWS", "cloud": "aws", "items": [
        ["inst-awsdr", "aws-dr", "10.200.0.4 · Pilot-Light"],
        ["inst-awsctl", "aws-ctl", "10.200.0.3 · Orchestrator"],
    ]},
    {"title": "확장·오류", "items": [
        ["design-kt", "KT 확장 설계", "HA/HPA · 제약 C1~C12"],
        ["trouble", "오류 확인 색인", "변수 → 확인 위치"],
    ]},
]


# ---------------------------------------------------------------------------
# 서비스 영역(도메인) — '서비스 기준' 렌즈의 대분류. 한 영역이 여러 도메인에 속할 수 있다.
# ---------------------------------------------------------------------------
DOMAINS = [
    {"id": "network", "name": "네트워크", "short": "망", "desc": "주소·라우팅·터널. 패킷이 어느 길로 가고 오는지."},
    {"id": "security", "name": "보안", "short": "보안", "desc": "누가 어디로 들어올 수 있는지. 보안그룹·WAF·키·공개 범위."},
    {"id": "web", "name": "웹 진입", "short": "웹", "desc": "사용자 요청이 들어오는 입구. 도메인·프록시·업스트림."},
    {"id": "compute", "name": "컴퓨트·k8s", "short": "k8s", "desc": "VM 과 쿠버네티스 노드를 만들고 붙이는 일."},
    {"id": "app", "name": "앱 배포", "short": "앱", "desc": "민원 앱을 어디에 몇 개 띄우고 어떻게 늘리는지."},
    {"id": "data", "name": "데이터베이스", "short": "DB", "desc": "원본 DB, 복제, 백업."},
    {"id": "dr", "name": "DR·관제", "short": "DR", "desc": "장애 판정, 승격, 되돌림."},
    {"id": "ops", "name": "접근·운영", "short": "운영", "desc": "노드 접속 경로와 운영 도구."},
]

AREA_DOMAINS = {
    "inst-s1.access": ["ops", "security"], "inst-s1.vmnet": ["network"],
    "inst-s1.wg": ["network", "security"], "inst-s1.cfd": ["web", "security"],
    "inst-controller.svc": ["compute"], "inst-controller.net": ["network"],
    "inst-controller.sg": ["security", "network"], "inst-controller.image": ["compute"],
    "inst-controller.server": ["compute"],
    "inst-cp1.k3s": ["compute"], "inst-cp1.cni": ["network", "compute"], "inst-cp1.app": ["app"],
    "inst-cp1.hpa": ["app", "compute"], "inst-cp1.argocd": ["app", "ops"],
    "inst-w1.agent": ["compute"],
    "inst-db01.mysql": ["data"], "inst-db01.backup": ["data", "dr"],
    "inst-ktedge.wg": ["network"], "inst-ktedge.nginx": ["web", "security"],
    "inst-ktedge.nat": ["security", "network"],
    "inst-ktw1.pre": ["compute"], "inst-ktw1.wg": ["network", "security"], "inst-ktw1.join": ["compute"],
    "inst-ktw1.ha": ["app", "web"], "inst-ktw1.hpa": ["app", "compute"],
    "inst-awsdr.wg": ["network"], "inst-awsdr.k3s": ["compute"], "inst-awsdr.mysql": ["data", "dr"],
    "inst-awsctl.api": ["dr", "ops"],
}

INSTANCE_SHORT = {
    "inst-s1": "s1", "inst-controller": "controller", "inst-cp1": "cp1", "inst-w1": "w1",
    "inst-db01": "db-01", "inst-ktedge": "kt-edge", "inst-ktw1": "kt-w1",
    "inst-awsdr": "aws-dr", "inst-awsctl": "aws-ctl",
}
INSTANCE_ORDER = list(INSTANCE_SHORT)
REFERENCE = [["overview", "전체 구성과 변수표"], ["design-kt", "KT 확장 설계"], ["trouble", "오류 확인 색인"]]


# ---------------------------------------------------------------------------
# *.sh 링크 — 화면 안의 경로·파일명이 자동으로 링크가 된다. file 은 content/scripts/ 아래(→ public/scripts/).
# 공개 저장소라 사본은 전부 읽고 비밀값 없음을 확인한 것만 둔다(S3 버킷 이름은 가림).
# ---------------------------------------------------------------------------
SCRIPTS = [
    {"keys": ["~/bin/openstack-vm.sh", "openstack-vm.sh"], "file": "s1/openstack-vm.sh", "host": "s1", "path": "~/bin/openstack-vm.sh", "status": "live"},
    {"keys": ["/opt/minwon-backup/run-backup.sh", "run-backup.sh"], "file": "db-01/run-backup.sh", "host": "db-01", "path": "/opt/minwon-backup/run-backup.sh", "status": "live"},
    {"keys": ["/opt/minwon-backup/backup-binlog.sh", "backup-binlog.sh"], "file": "db-01/backup-binlog.sh", "host": "db-01", "path": "/opt/minwon-backup/backup-binlog.sh", "status": "live"},
    {"keys": ["/opt/minwon-backup/transfer-binlog.sh", "transfer-binlog.sh"], "file": "db-01/transfer-binlog.sh", "host": "db-01", "path": "/opt/minwon-backup/transfer-binlog.sh", "status": "live"},
    {"keys": ["/opt/minwon-backup/transfer-full.sh", "transfer-full.sh"], "file": "db-01/transfer-full.sh", "host": "db-01", "path": "/opt/minwon-backup/transfer-full.sh", "status": "live"},
    {"keys": ["/usr/local/sbin/mysql-backup.sh", "mysql-backup.sh"], "file": "db-01/mysql-backup.sh", "host": "db-01", "path": "/usr/local/sbin/mysql-backup.sh", "status": "live"},
    {"keys": ["upload-binlog.sh"], "file": "aws-dr/upload-binlog.sh", "host": "aws-dr", "path": "/home/rocky/minwon-backup/upload-binlog.sh", "status": "live"},
    {"keys": ["upload-full.sh"], "file": "aws-dr/upload-full.sh", "host": "aws-dr", "path": "/home/rocky/minwon-backup/upload-full.sh", "status": "live"},
] + [
    {"keys": ["/opt/minwon-dr/" + n + ".sh", n + ".sh"], "file": "aws-dr/" + n + ".sh", "host": "aws-dr", "path": "/opt/minwon-dr/" + n + ".sh", "status": "live"}
    for n in ["preflight", "check-replica", "check-gtid", "check-fencing", "promote-mysql",
              "prepare-reverse-replication", "failback-precheck", "validate-replica", "mysql-reverse-tunnel"]
] + [
    {"keys": ["/root/kt-w1-preflight.sh", "kt-w1-preflight.sh"], "file": "kt-w1/kt-w1-preflight.sh", "host": "kt-w1", "path": "/root/kt-w1-preflight.sh", "status": "design",
     "generate": ["inst-ktw1", "pre", 0]},
    {"keys": ["tools/build.sh"], "url": "https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/tools/build.sh", "host": "저장소", "path": "tools/build.sh", "status": "live"},
    {"keys": ["/usr/local/bin/k3s-agent-uninstall.sh"], "url": "https://docs.k3s.io/installation/uninstall", "host": "k3s 공식 문서", "path": "k3s-agent-uninstall.sh (설치 시 자동 생성)", "status": "live"},
]


def static_config():
    """공개 페이지(#cfg-data)에 넣는 정적 설정 — 가이드 내용은 넣지 않는다."""
    return {"domains": DOMAINS, "measured": MEASURED,
            "extScripts": [{k: v for k, v in x.items() if k in ("keys", "url", "host", "path", "status")}
                           for x in SCRIPTS if "url" in x]}


def data():
    for pid in INSTANCE_ORDER:
        page = PAGES[pid]
        page["short"] = INSTANCE_SHORT[pid]
        for a in page["areas"]:
            key = pid + "." + a["id"]
            assert key in AREA_DOMAINS, "도메인 미지정: " + key
            a["domains"] = AREA_DOMAINS[key]
    for key in AREA_DOMAINS:
        pid, aid = key.split(".")
        assert any(a["id"] == aid for a in PAGES[pid]["areas"]), "없는 영역: " + key
    return {"measured": MEASURED, "vars": VARIABLES, "steps": STEPS, "pages": PAGES, "nav": NAV,
            "domains": DOMAINS, "instances": INSTANCE_ORDER, "reference": REFERENCE,
            "default": {"lens": "inst", "major": "inst-s1", "minor": "access"},
            "scripts": [{k: v for k, v in x.items() if k != "generate"} for x in SCRIPTS]}
