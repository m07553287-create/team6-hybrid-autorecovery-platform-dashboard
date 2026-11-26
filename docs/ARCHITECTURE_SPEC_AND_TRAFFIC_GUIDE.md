# 하이브리드 멀티클라우드 아키텍처 규격 및 트래픽 판별 가이드

> **문서 버전**: v2.1  
> **최종 갱신**: 2026-11-26  
> **프로젝트**: KT Cloud CI5 팀6 하이브리드 멀티클라우드 자동복구 플랫폼  

---

## 1. 내부 트래픽 vs 외부 트래픽 판별 및 라우팅 설정안

본 플랫폼은 외부 인터넷 사용자 요청과 내부 클라우드 간 동기화/관제 트래픽을 엄격히 구분하여 모니터링 및 보안 격리를 수행합니다.

### 1.1 트래픽 분류 기준표

| 구분 | 인입 경로 | 소스 IP / 인터페이스 | 부여 헤더 / 식별자 | 라우팅 및 보안 규칙 |
| :--- | :--- | :--- | :--- | :--- |
| **외부 트래픽 (North-South)** | 인터넷 ➔ Cloudflare WAF ➔ KT Edge | 공인 IP (`14.63.212.190:443`), `eth0` | `X-Traffic-Type: EXTERNAL`<br/>`X-Real-IP: <사용자IP>` | • Nginx ModSecurity WAF 검사<br/>• 10초 마이크로캐시 적용<br/>• DB 직접 접근 차단 (403) |
| **내부 트래픽 (East-West)** | WireGuard 메쉬망 (터널 A·B·C) | `10.200.0.0/24`, `wg-kt`, `wg0` | `X-Traffic-Type: INTERNAL` | • 터널 암호화(ChaCha20-Poly1305)<br/>• 온프렘 ↔ AWS 간 복구/관제<br/>• Prometheus 메트릭 수집 허용 |
| **격리 DB 백업 트래픽** | 내부 전용 데이터 네트워크 | `10.10.2.0/24` (`data-net`) | 전용 네트워크 세그먼트 | • 공인 인터넷 라우팅 차단<br/>• MySQL 8.4 GTID 복제 및 백업 전용 |

---

### 1.2 KT Cloud Edge Nginx 트래픽 자동 분류 설정안 (`traffic_classifier.conf`)

```nginx
# /etc/nginx/conf.d/traffic_classifier.conf

# 1. 인입 IP 대역에 따른 트래픽 분류
geo $remote_addr $traffic_type {
    default          "EXTERNAL";     # 외부 인터넷 및 일반 접속
    10.0.0.0/8       "INTERNAL";     # WireGuard 터널망 및 클라우드 내부망
    172.20.0.0/24    "INTERNAL";     # 온프레미스 K8s 앱망
    10.10.2.0/24     "INTERNAL";     # 온프레미스 DB 격리망
    192.168.0.0/16   "INTERNAL";     # 관리자 및 점프 호스트망
}

# 2. 업스트림 전달 시 판별 헤더 주입
proxy_set_header X-Traffic-Type $traffic_type;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

# 3. 액세스 로그 포맷에 트래픽 유형 명시
log_format traffic_analytics '[$time_local] type=$traffic_type client=$remote_addr '
                             'status=$status uri="$request_uri" upstream=$upstream_addr '
                             'latency=${request_time}s';

access_log /var/log/nginx/traffic_access.log traffic_analytics;
```

---

## 2. 각 클라우드별 추가 설치 및 가동 구성요소 정의

3대 클라우드 거점(KT Cloud Edge, 온프레미스 OpenStack/K8s, AWS DR)에 설치 및 가동 중인 구성요소와 역할 정의입니다.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 [KT Cloud Edge 관문]                                   │
│   • Nginx 1.24 (Reverse Proxy & WAF)   • ModSecurity v3 (OWASP CRS)                    │
│   • WireGuard (wg-kt: 10.200.0.1)      • traffic_classifier (geo 내부/외부 판별)         │
└────────────────────────────────────────────────────────────────────────────────────────┘
                       │                                    │
          [WireGuard 터널 A]                       [WireGuard 터널 C]
                       ▼                                    ▼
┌─────────────────────────────────────────┐  ┌───────────────────────────────────────────┐
│        [온프레미스 OpenStack + K8s]     │  │                  [AWS DR]                 │
│ • k8s-cp1 (172.20.0.86 / All-in-One):   │  │ • aws-dr (10.200.0.4 / Pilot-Light):      │
│   - K3s v1.37.2 (Control Plane & Worker)│  │   - K3s v1.37.2 (Standby ➔ L3 승격)       │
│   - Traefik L7 Ingress Controller       │  │   - MySQL 8.4 Replica (semi-sync / GTID)  │
│   - minwon-app (2 Replicas, 4c/6.5GB)   │  │   - minwon-app (평시 대기 ➔ 승격 시 기동) │
│ • db-01 (10.10.2.10 / 중앙 백업 DB):    │  │ • aws-ctl (10.200.0.3 / DR 관제):         │
│   - MySQL 8.4 Primary & Cinder 30GB     │  │   - FastAPI DR Orchestrator (3-Signal)    │
│   - 평시 백업 & AWS 쓰기 시 백업 수신   │  │   - Prometheus, Grafana, Loki             │
│ • ktci5 (10.10.10.8): cloudflared 터널  │  │   - Ansible 장애 복구 자동화 엔진         │
└─────────────────────────────────────────┘  └───────────────────────────────────────────┘
```

### 2.1 클라우드별 상세 컴포넌트 명세

| 클라우드 환경 | 호스트 / IP | 추가 설치 및 가동 구성요소 | 확정 역할 및 상세 기능 |
| :--- | :--- | :--- | :--- |
| **KT Cloud (Edge)** | `kt-edge`<br/>(`14.63.212.190`) | • **Nginx 1.24**<br/>• **ModSecurity v3**<br/>• **WireGuard (`wg-kt`)**<br/>• **traffic_classifier** | • 민원 접수 외부 트래픽 수신 및 TLS 1.3 암호화 종료<br/>• OWASP Core Rule Set 기반 웹 공격 탐지 및 차단<br/>• 외부 요청 판별 헤더 주입(`X-Traffic-Type: EXTERNAL`)<br/>• 온프렘(터널 A) 및 AWS(터널 C) 라우팅 |
| **온프레미스 (K8s)** | `k8s-cp1`<br/>(`172.20.0.86`) | • **K3s v1.37.2 (All-in-One)**<br/>• **Traefik Ingress**<br/>• **minwon-app (2 Replicas)**<br/>• **WireGuard Client (`wg0`)** | • 마스터 및 워커 단일 통합 노드 (4 vCPU / 6.5GB RAM)<br/>• 민원 접수 애플리케이션 안정 서빙 (`:30080 NodePort`)<br/>• 평시 `db-01 (10.10.2.10)`로 민원 데이터 커밋 |
| **온프레미스 (DB)** | `db-01`<br/>(`10.10.2.10`) | • **MySQL 8.4 LTS Primary**<br/>• **Cinder 30GB 영구 볼륨**<br/>• **GTID 복제 엔진** | • 온프레미스 및 AWS 공용 중앙 백업 대상 (Backup Target)<br/>• 평시: 온프레미스 파드 데이터 보관<br/>• **AWS DR 승격 시: AWS MySQL에서 쓰기 발생 시 10.10.2.10으로 백업 수신** |
| **온프레미스 (호스트)**| `ktci5`<br/>(`10.10.10.8`) | • **cloudflared** (Cloudflare Tunnel)<br/>• **WireGuard Mesh (`wg0`, `wg-kt`)** | • 아웃바운드 0-Trust 터널 연계<br/>• 외부 인바운드 포트 차단 상태로 도메인 보안 라우팅 |
| **AWS (DR 노드)** | `aws-dr`<br/>(`10.200.0.4`) | • **K3s v1.37.2 (Dormant)**<br/>• **MySQL 8.4 Replica (RO)**<br/>• **WireGuard (`wg-kt`, `wg0`)** | • 평시 읽기 전용 대기 (Pilot-Light, t3.small)<br/>• L3 페일오버 시: `read_only=OFF`로 Primary 승격<br/>• **승격 후 신규 쓰기 트랜잭션 ➔ 온프렘 `10.10.2.10`으로 무유실 백업 전송** |
| **AWS (관제 엔진)** | `aws-ctl`<br/>(`10.200.0.3`) | • **FastAPI DR Orchestrator**<br/>• **Prometheus / Grafana / Loki**<br/>• **Ansible Playbook 엔진** | • S1(앱)/S2(DB 복제)/S3(네트워크) 3-Signal 통합 관측<br/>• L1 파드 재시작, L2 Ansible 서비스 복구, L3 KT Edge 절체 자동 통제 |

---

## 3. DR 페일오버 및 DB 백업 흐름 규격

1. **평시 가동 상태**:
   - 민원 접수 ➔ KT Edge (`14.63.212.190`) ➔ 터널 A ➔ 온프렘 `k8s-cp1` (`minwon-app`) ➔ `db-01` (`10.10.2.10:3306`) 기록
   - `db-01` ➔ AWS DR MySQL (`10.200.0.4`)로 GTID 비동기/semi-sync 복제
2. **L3 재해 발생 (AWS DR 승격)**:
   - 온프렘 장애 감지 시 KT Edge가 업스트림을 **터널 C(AWS)**로 전환
   - AWS DR MySQL이 Primary(RW)로 승격되어 민원 접수 처리 지속
   - **AWS에서 발생한 신규 쓰기 트랜잭션은 온프렘 백업 대상인 `10.10.2.10 (db-01)`으로 실시간 백업 전송**
3. **평시 원복 (Failback)**:
   - `10.10.2.10`에 축적된 무유실 백업 데이터를 기반으로 온프렘 클러스터 복원 및 원복 완료
