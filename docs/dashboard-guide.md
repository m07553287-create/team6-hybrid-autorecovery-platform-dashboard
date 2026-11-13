# 🛡️ FIGTEAM 하이브리드 클라우드 통합 운영 대시보드 상세 명세서

> **대시보드 접속 URL**: [https://figteam.ktci5.kr](https://figteam.ktci5.kr)  
> **GitHub 저장소**: [team6-hybrid-autorecovery-platform-dashboard](https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard)  
> **아키텍처 버전**: v2.5.1 / v3.0 Drawio 명세 100% 구현  
> **문서 목적**: 노션(Notion) 임베드 및 팀 공유용 대시보드 파트별 기술 명세 및 운영 가이드

---

## 📌 대시보드 핵심 구조 요약

FIGTEAM 포털은 **3대 하이브리드 거점(KT Cloud · 온프렘 OpenStack · AWS)**을 단일 화면에서 관제하고 제어하는 CMP(Cloud Management Platform)이자 DR 장애복구 관제 센터입니다.

```
[ 사용자 브라우저 ]
        │ HTTPS (443)
        ▼
[ Cloudflare Pages ] ─── figteam.ktci5.kr (정적 대시보드 화면 서빙)
        │
        ├─▶ [온프렘 터널 (minwon-tunnel)] ─── figteam-api.ktci5.kr:18088 (API/SSO 백엔드)
        │         ├─ OpenStack Nova / Neutron API 연동
        │         ├─ KT Cloud OpenAPI 연동
        │         └─ 실시간 터미널 / 시스템 제어 액션
        │
        └─▶ [3자 WireGuard 풀메쉬 (10.200.0.0/24)]
                  ├─ 터널 A (평시 트래픽): KT Cloud Edge ↔ 온프렘 K3s
                  ├─ 터널 B (관제 및 복제): 온프렘 MySQL ↔ AWS Replica / 관제
                  └─ 터널 C (재해 복구): KT Cloud Edge ↔ AWS DR K8s
```

---

## 🖥️ 대시보드 파트별 세부 설명

---

### 파트 1. 최상단 네비게이션 헤더 (Global Header)

대시보드 최상단에서 전체 플랫폼의 실시간 연결 상태를 한눈에 파악하고 로그인 세션을 관리합니다.

* **브랜드 로고 & 플랫폼 태그**: `FIGTEAM CMP` / `HYBRID CLOUD`
* **3대 거점 실시간 헬스 칩 (Health Chips)**:
  * 🟢 **KT Cloud**: `14.63.212.190` (Edge-GW Nginx+WAF 정상)
  * 🟢 **온프레미스 (OpenStack)**: `10.10.10.8` (K3s 4노드 및 MySQL Primary 활성)
  * 🟡 **AWS DR 리전**: `ap-northeast-2` (Pilot-Light 대기 중)
* **로그인 사용자 및 세션 제어**: 접속자 권한(Admin) 표시 및 원클릭 안전 로그아웃

---

### 파트 2. 좌측 사이드바 & 단일 도메인 원클릭 SSO

폐쇄망 내부 도구들을 별도의 포트 암기 없이 단일 도메인(`*.ktci5.kr`)으로 이동할 수 있는 통합 게이트웨이입니다.

| 메뉴명 | 엔드포인트 URL | 기술 스택 및 역할 |
| :--- | :--- | :--- |
| **개요 (Overview)** | `/#overview` | 3대 거점 자원 요약 카드 및 전체 상태 대시보드 |
| **🛡️ 운영 대시보드** | `/#dr` | 2D 토폴로지 동적 제어, 9단계 시나리오, 실시간 시스템 액션 |
| **☁️ 온프렘 VM 관리** | `/#osvm` | OpenStack 인스턴스 전원 제어, OVN 네트워크 구조도 |
| **🌐 KT Cloud VM 관리** | `/#ktvm` | KT Cloud OpenAPI 기반 Edge-GW 가상머신 자원 관제 |
| **🚀 Argo CD** | `/#argocd` | GitOps 기반 폐쇄망 무중단 배포 파이프라인 (SSO 연동) |
| **📈 Grafana** | `/#grafana` | Prometheus 수집 메트릭(Node, WG, MySQL, Nginx) 관제 |
| **📋 Horizon 콘솔** | `/#horizon` | OpenStack 정식 웹 GUI 관리 콘솔 통합 프록시 |

---

### 파트 3. 운영 대시보드 & DR 관제 콘솔 (`/#dr`) ★ 핵심 기능

민원불패 v3.0 Drawio 아키텍처 토폴로지를 1:1로 시각화하고 실시간 인터랙티브 제어를 제공합니다.

#### 1) 상단 컨트롤 바 (Control Bar)
* **`[📋 콘솔확인]` 버튼**:
  * 클릭 시 **통합 운영 진단 모달(`console-modal`)** 팝업.
  * 3-Signal 프로브(S1 WAF, S2 호스트, S3 터널) 상태, WireGuard 터널 핸드셰이크, MySQL GTID 지연(Lag 0초), K8s 파드 상태 및 실시간 시스템 로그 스트림을 즉시 검증.
* **`[📡 도달 범위 & 격리선 표시]` 버튼**:
  * 2D 토폴로지 캔버스 상에 **OpenStack OVN 3단 격리선(외부망/내부망/폐쇄망)**과 **WireGuard 터널별 도달 범위**를 보라색 오버레이로 온/오프 토글.
* **`[🗺️ 도달 범위 검증 모달]` 버튼**:
  * 폐쇄망 격리 검증 매트릭스(Argo CD / Grafana 도달 경로 및 차단 상태) 팝업.
* **트래픽 흐름 속도 인디케이터 (Flow Velocity Gauge)**:
  * 실시간 트래픽 양과 RTT를 4단계 게이지와 텍스트로 표기 (예: `⚡ 180 req/s · RTT 4.2ms [VERY FAST 🟢]`).

#### 2) 7단계 시뮬레이션 제어기 (Scenario Buttons)
단계 미선택 시 기본 전체 흐름이 상시 작동하며, 특정 단계 버튼을 누르면 해당 장애/복구 흐름이 최우선 적용됩니다.

1. **🌐 전체 통합 흐름 (기본 정상)**: 평시 KT Edge ➔ 터널 A ➔ 온프렘 정상 처리 및 터널 B 복제.
2. **🟡 2. L1: Pod 크래시 자가치유**: Kubelet 초 단위 감지 및 컨테이너 무중단 재기동.
3. **🟠 3. L2: 서비스 1분 무응답**: 대민 S1 실패 ➔ AWS 터널 B를 통한 Ansible 자동 플레이북 재기동 (≤3분).
4. **🔵 4. 경로장애 (터널 A 단절)**: S1·S3 실패, S2 정상 ➔ 터널 C·B 우회 (온프렘 인스턴스 정상이므로 **DB 승격 금지**).
5. **🔴 5. L3: 온프렘 전면 마비**: S1·S2·S3 동시 실패 ➔ Watchdog 자가 펜싱 ➔ AWS Replica 승격 (`super_read_only=OFF`).
6. **🟣 6. L4: 복구 및 원복 (Failback)**: 역방향 GTID 스트리밍 동기화 ➔ 온프렘 Primary 재승격.
7. **⚫ 7. Black Sky (전면 불능)**: 3대 거점 동시 마비 시 Cloudflare 엣지 ➔ GitHub Pages(`dr.ktci5.kr`) 0초 정적 접수 폴백.

#### 3) 인터랙티브 2D 토폴로지 캔버스 (`t3-host`)
* **3단 망분리 영역 표기**:
  * 🌐 **[외부망 DMZ]**: `br-ex` (Floating IP 대역, WireGuard 터널 종단)
  * 🏢 **[내부망 SERVICE]**: `net-k3s` (`10.10.1.0/24`, web/api 파드 클러스터)
  * 🔒 **[폐쇄망 ISOLATED]**: `net-data` (`10.10.2.0/24`, No-Gateway 완전 격리 MySQL 원장)
* **노드 클릭 실시간 시스템 제어 액션 (`t3-card`)**:
  * 구성도의 장비를 클릭하면 실시간 액션 툴바가 활성화되어 실제 명령 수행 가능:
    * **Edge-GW / WG**: `[🔄 KT Edge 터널 A ↔ C 절체]`
    * **MySQL Primary**: `[🛑 Watchdog 펜싱 실행 (쓰기 차단)]` / `[🟢 복구]`
    * **AWS Replica**: `[⚡ AWS Replica 승격 (super_read_only=OFF)]`
    * **Web / API Pod**: `[💥 L1 파드 크래시 유발 (/chaos/crash)]` / `[↻ 롤링 재시작]`
    * **OpenStack VM**: `[🛑 VM 전원 끄기 (Stop)]` / `[⚡ 전원 켜기 (Start)]`

#### 4) 우측 3단 탭 패널
* **흐름 단계 (`#dc-tab-flow`)**: Hop 1부터 18까지 패킷 이동 단계를 **100% 수동 모드**로 클릭하며 확인 (사용자가 클릭한 단계에 정지하여 세부 경로 관찰).
* **대응 절차 (`#dc-tab-sop`)**: 상황별 표준운영절차(SOP) 매뉴얼 전문 제공.
* **모의훈련 (`#dc-tab-drill`)**: 카오스 엔지니어링 주입 커맨드 콘솔.

---

### 파트 4. OpenStack 구조 및 인프라 관리 (`/#osvm`)

온프레미스 프라이빗 클라우드의 물리 노드와 가상머신, OVN 가상 네트워크를 실시간 동기화합니다.

* **OpenStack VM 목록 & 라이프사이클 제어**:
  * `t1-vm1` (Edge-GW), `t1-vm2` (Controller/K8s Master), `t1-vm3` (Compute Worker), `t1-vm4` (MySQL Primary)
  * 인스턴스 전원 시작(Start), 정지(Stop), 재부팅(Reboot), 콘솔 로그(Console Log) 조회
* **OVN 가상 네트워크 토폴로지 (osview.js)**:
  * OpenStack Neutron OVN의 Geneve 터널링, 로컬 라우터, 브리지, 보안 그룹을 SVG 벡터 그래픽으로 렌더링.
* **폐쇄망 서비스 기본 설정 가이드**:
  * 외부 인터넷 게이트웨이가 차단된 폐쇄망 MySQL 및 K8s 클러스터에 안전하게 접근하는 WireGuard 점프 터널 가이드 제공.

---

### 파트 5. KT Cloud VM 관리 (`/#ktvm`)

KT Cloud KOR-Central A 존에 프로비저닝된 진입점 가상머신의 실시간 스펙을 조회합니다.

* **인스턴스명**: `kt-edge-dr-01`
* **공인 IP / 사설 IP**: `14.63.212.190` / `172.27.0.160`
* **스펙**: 1 vCPU / 2,048 MB RAM / 20 GB 루트 디스크 (Rocky Linux 8.10)
* **포트포워딩 매핑**:
  * SSH (`22000 ➔ 22`), HTTP (`80 ➔ 80`), HTTPS (`443 ➔ 443`), WireGuard (`51820/udp ➔ 51820/udp`)

---

## 🔗 노션(Notion) 임베드 활용 방법

팀 노션 워크스페이스에 이 문서를 깔끔한 카드 및 뷰어로 삽입하는 방법입니다.

1. **GitHub Markdown 직접 임베드**:
   * 아래 GitHub 원본 파일 URL을 복사합니다:
     ```text
     https://github.com/m07553287-create/team6-hybrid-autorecovery-platform-dashboard/blob/main/docs/dashboard-guide.md
     ```
   * 노션 페이지의 빈 줄에 붙여넣기(`Cmd+V`) 후 **`북마크 생성(Create bookmark)`** 또는 **`임베드 생성(Create embed)`**을 선택합니다.
2. **실시간 대시보드 웹 임베드**:
   * 대시보드 주소 [https://figteam.ktci5.kr](https://figteam.ktci5.kr) 를 노션에 붙여넣고 **`임베드 만들기(Create embed)`**를 선택하면, 노션 페이지 안에서 바로 대시보드 조작이 가능합니다.
