# 📋 KT Cloud 진입점 2인 분업 가이드 및 통합 검증서 (Integration Test)

> **팀 저장소**: [team6-hybrid-autorecovery-platform-dashboard](https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard)  
> **대상 인프라**: KT Cloud Edge-GW VM (`kt-edge-dr-01` · Rocky Linux 8.10 · `<KT_EDGE_PUBLIC_IP>`)  
> **협업 작업자**: 작업자 A (인프라 · 네트워크 · VPN) / 작업자 B (웹 프록시 · WAF · DR 스위칭)  
> **문서 버전**: v1.1 (마스킹 보안 표준 적용본)

---

## 1. 역할 분담 총괄표

| 구분 | 작업자 A (인프라 · 네트워크 · VPN) | 작업자 B (웹 프록시 · WAF · DR 스위칭) |
| :--- | :--- | :--- |
| **핵심 미션** | **"진입점 서버를 띄우고, 터널 길을 뚫는 작업"** | **"민원인 트래픽을 받고, 방어하고, 넘기는 작업"** |
| **1단계: 인프라 구축** | ✅ KT Cloud 키페어(`edgekey`) 생성<br>✅ KT Cloud API 연동 및 트러블슈팅 해결 완료<br>✅ VM(`kt-edge-dr-01`, Rocky 8.10, 1vCPU/2GB) 생성<br>✅ 공인 IP 바인딩 및 5개 포트 포워딩 개방<br>⏳ IaC 코드(API 스크립트/Terraform) 레포 정리 | ✅ A의 인프라 개통 및 접속 정보 인계 완료<br>✅ 원격 SSH 접속 검증 완료 (`edgekey.pem`) |
| **2단계: OS/보안 기초** | ✅ OS 내부 방화벽(`firewalld`) 포트 개방 (A/B 포트 전체)<br>✅ 커널 패킷 포워딩(`net.ipv4.ip_forward=1`) 영구 활성화 | *(OS 방화벽은 A가 전담 관리하므로 충돌 방지를 위해 미접근)* |
| **3단계: 핵심 서비스** | ✅ **WireGuard VPN 허브** 설치 및 키 발급<br>✅ `wg0` 인터페이스 구성 (`10.200.0.1/24`)<br>✅ 온프렘(`.2`), AWS(`.3`) 3자 Peer 연결 및 개통 | ✅ **Nginx** 설치 및 HTTPS/TLS 종료 설정<br>✅ **ModSecurity (WAF)** 연동 및 SQLi 차단 룰 적용<br>✅ **Upstream 설정** (평시 온프렘으로 프록시) |
| **4단계: DR/관제 연동** | ✅ `node_exporter` / WireGuard 메트릭 노출 (`:9100`)<br>✅ C1 라벨 (`site="ktcloud"`, `service="wireguard"`) 적용<br>✅ 전체 설정 **Ansible 플레이북** 코드화 | ✅ **DR 전환 스위치** (`Upstream 교체 + 핫리로드`) 구현<br>✅ Orchestrator/Ansible 호출용 전환 스크립트 준비<br>✅ C1 라벨 (`site="ktcloud"`, `service="edge-nginx"`) 적용 |
| **주요 작업 경로** | `/etc/wireguard/`, `/etc/sysctl.conf`, `firewalld` | `/etc/nginx/`, `/etc/nginx/modsec/`, `/opt/scripts/` |
| **담당 포트** | `22/tcp` (SSH), `51820/udp` (WireGuard), `9100/tcp` (Exporter) | `80/tcp` (HTTP), `443/tcp` (HTTPS), `30080/tcp` (DR NodePort) |

---

## 2. A ↔ B 사전 합의 인터페이스 계약표 (충돌 방지)

| 항목 | 합의 값 (표준 규격) | 비고 |
| :--- | :--- | :--- |
| **서버 접속 정보** | `ssh -i <edgekey.pem> root@<KT_EDGE_PUBLIC_IP>` | 작업자 A가 생성 후 작업자 B에게 키/IP 인계 완료 |
| **호스트명 / 사설망** | `kt-edge-dr-01` / `172.27.0.160` (Rocky Linux 8.10) | KT Cloud KOR-Central A 기본 서브넷 |
| **WireGuard 터널 IP** | • **KT Edge (본 서버)**: `10.200.0.1/24`<br>• **온프렘 게이트웨이**: `10.200.0.2`<br>• **AWS 관리망/DR**: `10.200.0.3` | VPN 세팅 중이더라도 Nginx Upstream 목적지 IP를 사전 작성 가능 |
| **Nginx 평시 목적지** | 온프렘 MetalLB VIP 또는 WireGuard 경유 `10.200.0.2:30080` | C2 계약(`ip-ports.yaml`) 준수 |
| **Nginx DR 목적지** | AWS EC2 Pilot-Light `10.200.0.3:30080` | 온프렘 장애 시 스위칭 타겟 |
| **공통 라벨 (C1)** | `site: "ktcloud"` / `service: "edge-nginx"` (또는 `wireguard`) | Prometheus 메트릭·인벤토리·GitHub CI 검증용 |
| **파일 수정 경계** | **작업자 A는 `/etc/nginx/` 수정 금지**<br>**작업자 B는 `/etc/wireguard/` 및 `firewalld` 수정 금지** | 동일 VM 동시 작업 시 설정 덮어쓰기 완전 방지 |

---

## 3. 일자별 작업 내역서

### # 11/12 작업

#### 작업자 A (인프라 · 네트워크)
1. KT Cloud 키페어 발급(`edgekey.pem`) 및 작업자 B에게 안전 인계.
2. 팀원들에게 AWS IAM 사용자 권한 추가 및 역할 부여.
3. 서브넷 및 인스턴스(`kt-edge-dr-01`) 생성.
   - **트러블슈팅**: KT Cloud의 경우 신규 커스텀 서브넷 생성 시 라우팅 제한 발생 → 기본 서브넷(`172.27.0.0/24`)을 활용하도록 조정하여 해결.

#### 작업자 B (웹 프록시 · WAF)
1. 작업자 A로부터 `edgekey.pem` 및 공인 IP 수령 후 SSH 원격 로그인 검증 완료.
2. Nginx 및 ModSecurity v3(WAF) 컴파일 및 Rocky Linux 8.10 패키지 사전 조사.
3. C2 계약(`ip-ports.yaml`) 기반 평시 Upstream(`10.200.0.2:30080`) 및 DR Upstream(`10.200.0.3:30080`) 아키텍처 매핑 정의.

---

### # 11/13 작업

#### 작업자 A (인프라 · 네트워크 · WireGuard 개통)
1. **OS 및 보안 방화벽 설정 (2단계)**
   - 커널 IP 포워딩 활성화: `sysctl -w net.ipv4.ip_forward=1` (`/etc/sysctl.conf` 영구 반영)
   - `firewalld` 포트 개방 및 인터페이스 마스커레이딩 활성화:
     ```bash
     firewall-cmd --permanent --add-port=22/tcp --add-port=51820/udp --add-port=9100/tcp
     firewall-cmd --permanent --add-port=80/tcp --add-port=443/tcp --add-port=30080/tcp
     firewall-cmd --permanent --add-masquerade
     firewall-cmd --reload
     ```
2. **WireGuard VPN 3자 풀메쉬 터널 개통 (3단계)**
   - `wireguard-tools` 설치 및 KT Edge 키 발급 (`wg genkey | tee privatekey | wg pubkey > publickey`).
   - `/etc/wireguard/wg0.conf` 작성 (`Address = 10.200.0.1/24`, `ListenPort = 51820`).
   - 온프렘 게이트웨이(`.2`) 및 AWS 관리망(`.3`) Peer 등록 후 서비스 기동 (`systemctl enable --now wg-quick@wg0`).
   - **[검증 1] 통과**: `wg show` 핸드셰이크 수초 이내 갱신 확인 및 `10.200.0.2`, `10.200.0.3` 양방향 ping 통신 성공.
3. **관제 메트릭 연동 (4단계)**
   - `node_exporter` 데몬 기동 (`:9100`) 및 Prometheus C1 라벨 적용 (`site="ktcloud"`, `service="wireguard"`).

#### 작업자 B (웹 프록시 · WAF · DR 스위칭)
1. **Nginx 웹 프록시 및 TLS 종료 구성 (3단계)**
   - Nginx 설치 및 HTTP(80) ➔ HTTPS(443) 301 강제 리다이렉트 설정.
   - HTTPS/TLS 인증서 구성 및 WireGuard 터널 A 연동 프록시 설정 (`/etc/nginx/conf.d/minwon.conf`):
     ```nginx
     upstream minwon_backend {
         server 10.200.0.2:30080 max_fails=2 fail_timeout=3s; # 평시 온프렘
     }
     server {
         listen 443 ssl http2;
         server_name minwon.ktci5.kr <KT_EDGE_PUBLIC_IP>;
         location / {
             proxy_pass http://minwon_backend;
             proxy_set_header Host $host;
             proxy_set_header X-Real-IP $remote_addr;
         }
     }
     ```
2. **ModSecurity (WAF) 연동 및 보안 룰 검증 (3단계)**
   - ModSecurity v3 및 OWASP CRS (Core Rule Set) 연동 (`SecRuleEngine On`).
   - **[검증 2] 통과**: 정상 민원 접속(200 OK) 확인 및 SQL Injection 공격 탐지 시 즉시 **403 Forbidden** 차단 확인.
3. **DR Upstream 무중단 전환 스위치 구현 (4단계)**
   - 장애 대응 스위칭 스크립트 작성 (`/opt/scripts/dr-switch.sh`):
     ```bash
     #!/bin/bash
     # 온프렘 장애 시 AWS DR 노드로 Upstream 핫스왑 전환
     sed -i 's/10.200.0.2:30080/10.200.0.3:30080/g' /etc/nginx/conf.d/minwon.conf
     nginx -s reload
     echo "[DR] Upstream successfully switched to AWS (10.200.0.3:30080)"
     ```
   - **[검증 3] 통과**: 스위칭 실행 시 연결 단절 없이 즉각 AWS Replica 컨테이너로 트래픽 인계 확인.
4. **관제 라벨 적용 (4단계)**
   - Nginx `stub_status` 메트릭 노출 및 C1 라벨 태깅 (`site="ktcloud"`, `service="edge-nginx"`).

---

## 4. 합동 최종 검증 (Integration Test) 실행 매뉴얼

| 순서 | 검증 항목 | 담당자 | 검증 명령어 및 성공 기준 |
| :---: | :--- | :---: | :--- |
| **1** | **WireGuard 3자 터널 핸드셰이크** | 작업자 A | ```bash\n# KT Edge에서 실행\nwg show\nping -c 3 10.200.0.2 # 온프렘\nping -c 3 10.200.0.3 # AWS\n```<br>👉 **성공 기준**: `latest handshake`가 2분 이내이며 패킷 유실률 0%, RTT < 10ms. |
| **2** | **외부 HTTPS 접속 & WAF 차단** | 작업자 B | ```bash\n# 1) 정상 접속 확인 (200 OK)\ncurl -k -I https://<KT_EDGE_PUBLIC_IP>/\n\n# 2) SQL Injection 공격 시뮬레이션 (403 Forbidden)\ncurl -k -I "https://<KT_EDGE_PUBLIC_IP>/?id=1'%20OR%20'1'='1"\n```<br>👉 **성공 기준**: 정상 요청 200 OK / 공격 요청 403 Forbidden 즉시 반환 및 감사 로그 기록. |
| **3** | **DR Upstream 스위칭 테스트** | 작업자 B<br>+ 작업자 A | ```bash\n# 전환 스크립트 실행\n/opt/scripts/dr-switch.sh\n\n# 전환 후 트래픽 수신처 확인\ncurl -k https://<KT_EDGE_PUBLIC_IP>/api/health\n```<br>👉 **성공 기준**: `nginx -s reload` 시 커넥션 끊김 없이 응답 서버가 AWS 노드로 0초 전환. |
| **4** | **IaC 재현성 검증** | 작업자 A<br>+ 작업자 B | ```bash\n# Ansible 플레이북 문법 및 드라이런 검증\nansible-playbook -i inventory kt-edge-provision.yml --syntax-check\n```<br>👉 **성공 기준**: 수동 설정 일체가 GitHub 코드로 영구 반영되어 신규 VM 생성 시 1회 커맨드로 복제 가능. |
