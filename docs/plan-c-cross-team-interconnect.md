# 📋 나의 오픈스택 ↔ 타 팀 VM/쿠버네티스 환경 연결 조성안 (Plan C)

> **문서 목적**: 동일 실습/센터 내 타 팀의 OpenStack VM 및 K8s 클러스터와 안전하게 통신하고 상호 재해복구(Mutual DR)를 수행하는 3번째 비상 연계 전략(Plan C) 수립  
> **적용 대상**: 내 오픈스택 (`192.168.120.160` / `172.20.0.0/24`) ↔ 타 팀 오픈스택/쿠버네티스 환경  
> **버전**: v1.0 (2026-11-13)

---

## 1. Plan C의 정의 및 추진 배경

### ① 왜 Plan C(타 팀 연계)가 필요한가?
* **기존 Plan A (평시)**: 내 오픈스택 K8s 3노드 ↔ KT Cloud Edge-GW (터널 A)
* **기존 Plan B (클라우드 DR)**: 온프렘 전면 마비 시 ➔ AWS EC2/K8s Replica 승격 (터널 C)
* **신규 Plan C (상호 백업 및 서비스 연계 - Cross-Team Mutual DR)**:
  * **AWS 클라우드 비용을 최소화**하거나, 상용 클라우드마저 장애가 발생하는 극한 상황 대비.
  * 실습 센터 내 **다른 팀의 오픈스택 VM 자원을 상호 예비 노드(Mutual Standby)로 활용**하여 무비용 고가용성 보장.
  * 타 팀의 마이크로서비스(예: AI 분석, 결제, 공공 데이터 연계)와 내 민원 접수 시스템 간의 **안전한 폐쇄망 데이터 통신** 구현.

---

## 2. 3대 핵심 아키텍처 과제 및 해결 방안

```
[ 나의 오픈스택 (FIGTEAM) ]                       [ 다른 팀 오픈스택 (Team X) ]
 ├─ k8s-cp1 (172.20.0.86)                          ├─ team-k8s-cp (172.20.0.x / 충돌 위험!)
 ├─ k8s-w1, w2 (172.20.0.x)                        ├─ team-k8s-w1, w2
 └─ GW VM (FIP 192.168.120.226)                    └─ GW VM (FIP 192.168.120.240)
         │                                                 │
         │  WireGuard 터널 D (10.200.10.1 ↔ 10.200.10.2)   │
         └───────────────── P2P 암호화 터널 ────────────────┘
                      (양 팀 L2 격리 및 IP 충돌 완전 해소)
```

### 과제 1. 내부 사설망 IP 충돌 방지 (Overlap IP Resolution)
* **문제점**: 각 팀이 OpenStack 기본값이나 동일한 대역(`172.20.0.0/24` 또는 `10.0.0.0/24`)을 내부망으로 사용할 경우 라우팅 충돌 발생.
* **해결책 (WireGuard P2P 가상 중계망 `10.200.10.0/24`)**:
  * 양 팀의 내부 사설 IP를 직접 노출하지 않고, 각 팀 게이트웨이에 **WireGuard 터널 IP(`내 팀: 10.200.10.1`, `타 팀: 10.200.10.2`)**를 할당하여 통신.
  * 1:1 NAT 및 특정 서비스 포트 포워딩으로 내부 IP 대역 충돌을 100% 원천 차단.

### 과제 2. 보안 격리 및 최소 권한 접근 (Zero-Trust Segmentation)
* **문제점**: 다른 팀 VM과 통신할 때 내 핵심 데이터베이스(MySQL Primary 원장)나 K8s 관리 포트(6443)가 노출될 위험.
* **해결책 (OpenStack 보안 그룹 & K8s NetworkPolicy)**:
  * **OpenStack 보안 그룹 (`sg-cross-team`)**:
    * 허용 포트: WireGuard 통신용 `51820/udp`, 서비스 연계용 `30080/tcp`(HTTP/HTTPS 프록시).
    * 차단: MySQL(`3306`), K8s API(`6443`), SSH(`22`)는 타 팀 대역 접근 엄격 차단.
  * **K8s NetworkPolicy**: 타 팀 네임스페이스의 인그레스 트래픽은 특정 API 엔드포인트(`/api/v1/cross/*`)로만 제한.

### 과제 3. 쿠버네티스 서비스 디스커버리 (K8s Service Mesh / DNS)
* 타 팀 K8s 클러스터의 서비스를 내 K8s 파드에서 호출하기 위해 CoreDNS의 `Corefile`에 조건부 포워딩 등록:
  ```text
  teamX.local:53 {
      errors
      cache 30
      forward . 10.200.10.2
  }
  ```
* 내 파드에서 `http://auth.teamX.local:30080` 형태로 타 팀 서비스를 일반 내부 도메인처럼 호출 가능.

---

## 3. 세부 단계별 구축 실행 절차 (Implementation Steps)

### 1단계: OpenStack 인프라 자원 준비 (내 오픈스택)
1. 타 팀 전용 통신 보안 그룹 생성:
   ```bash
   openstack security group create sg-cross-team --description "Cross-team interconnection security group"
   openstack security group rule create --proto udp --dst-port 51820 sg-cross-team # WireGuard
   openstack security group rule create --proto tcp --dst-port 30080 sg-cross-team # K8s Service NodePort
   openstack security group rule create --proto icmp sg-cross-team                # Health Ping
   ```
2. 외부망(`ext-net`, `192.168.120.0/24`)을 통해 타 팀 게이트웨이와 L3 도달성 확보 (Floating IP 연계).

### 2단계: 양 팀 간 WireGuard 터널 D (`10.200.10.0/24`) 개통
* **내 오픈스택 게이트웨이 (`/etc/wireguard/wg-team.conf`)**:
  ```ini
  [Interface]
  Address = 10.200.10.1/24
  ListenPort = 51820
  PrivateKey = <내_팀_개인키>

  [Peer]
  PublicKey = <타_팀_공용키>
  Endpoint = 192.168.120.240:51820  # 타 팀 Floating IP
  AllowedIPs = 10.200.10.2/32, 10.30.0.0/16 # 타 팀 허용 서비스 대역
  PersistentKeepalive = 25
  ```
* **핸드셰이크 검증**: `ping -c 3 10.200.10.2` (RTT < 2ms 무손실 확인).

### 3단계: K8s 서비스 엔드포인트 연동 (Argo CD GitOps 등록)
1. 타 팀 서비스를 가리키는 외부 서비스 엔드포인트 매니페스트(`external-team-svc.yaml`) 등록:
   ```yaml
   apiVersion: v1
   kind: Service
   metadata:
     name: team-x-service
     namespace: minwon
   spec:
     type: ExternalName
     externalName: 10.200.10.2
   ```
2. 내 민원 접수 서비스 파드가 `team-x-service`를 통해 타 팀의 VM/파드 기능을 호출하도록 연계.

---

## 4. 재해 복구(DR) 시나리오: Plan C 동작 매커니즘

| 상황 | 장애 단계 | Plan C 대응 동작 | 목표 RTO/RPO |
| :--- | :---: | :--- | :---: |
| **내 K8s Worker 장애** | **L2/L3 부분 장애** | 내 트래픽 일부를 WireGuard 터널 D를 통해 **타 팀 K8s의 예비 파드(Pilot-Light)**로 즉각 오프로딩 | RTO < 30초<br>RPO = 0 |
| **AWS DR 비용 절감 모드** | **비용 최적화** | 고비용 AWS 대신 **타 팀 오픈스택을 2차 DR 대기소**로 지정하여 상호 백업 체계 유지 | 월 비용 $0<br>고가용성 유지 |
| **타 팀 서비스 장애 지원** | **상호 부조** | 타 팀 시스템 장애 시 내 오픈스택 유휴 자원을 활용하여 타 팀의 핵심 파드를 임시 호스팅 | 공생 협력 체계 |

---

## 5. 결론 및 기대 효과

1. **완벽한 독립성 보장**: 양 팀의 오픈스택 계정이나 DB 패스워드를 공유할 필요 없이, 오직 암호화된 터널과 화이트리스트 포트로만 안전하게 협업.
2. **비용 0원의 무중단 아키텍처**: AWS 인프라 비용 부담 없이도 온프레미스 간 상호 백업(Plan C)을 구축하여 심화 프로젝트 평가 시 **"다계층 복원력(Multi-Tier Resilience)"** 만점 기준 충족.
3. **대시보드 통합 연동**: 대시보드(`figteam.ktci5.kr/#dr`) 2D 토폴로지에 **터널 D (Cross-Team)** 배지를 추가하여 실시간 통신 및 절체 상태를 시각적으로 입증 가능.
