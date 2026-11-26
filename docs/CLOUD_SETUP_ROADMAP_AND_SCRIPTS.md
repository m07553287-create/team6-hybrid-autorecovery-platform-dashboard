# 하이브리드 멀티클라우드 설정 순서 로드맵 및 실행 가이드

> **문서 버전**: v2.1  
> **적용 원칙**: **모든 설정은 기존 인프라 설정을 100% 유지하고 필요한 구성요소만 "추가(Add-on)"**  
> **자동화 우선순위**: **1순위 테라폼(Terraform)** ➔ **불가 시 쉘 스크립트(`sh`) 또는 대체 방안 적용**  

---

## 1. 클라우드별 설정 순서 요약 (해야 할 일)

```
[설정 실행 파이프라인]

  [1. KT Cloud Edge 관문] ──▶ [2. 온프레미스 OpenStack/K8s] ──▶ [3. AWS DR 백업/관제]
  - 트래픽 판별 모듈 추가     - db-01 백업 수신 계정 설정     - 승격 시 역방향 백업 연동
  - WAF 룰셋 검증           - All-in-One K8s 트래픽 인지     - Terraform 보안그룹 관리
```

---

## 2. 클라우드별 상세 설정 순서 및 설치 방안

### a. KT Cloud 설정 순서 (KT Cloud Edge 관문)

KT Cloud는 D1 인프라 특성상 VM 재성성을 방지하고 기존 WireGuard 터널을 온전히 보존하기 위해, **무중단 In-place `sh` 스크립트를 1순위로 적용**합니다.

1. **설정 순서**:
   - **Step 1**: 기존 Nginx 설정 백업 (`/etc/nginx/conf.d/` 보존)
   - **Step 2**: 내부/외부 트래픽 자동 판별 모듈(`traffic_classifier.conf`) 추가
   - **Step 3**: 업스트림 프록시 헤더 주입 설정(`X-Traffic-Type`, `X-Real-IP`) 반영
   - **Step 4**: Nginx 문법 검사(`nginx -t`) 후 무중단 리로드(`nginx -s reload`)
2. **실행 스크립트 (`sh`)**:
   ```bash
   # KT Cloud Edge-GW VM 접속 후 실행
   sudo bash scripts/setup_ktcloud_edge_addons.sh
   ```
3. **테라폼 연계 (IaC)**:
   - 신규 VM 프로비저닝 시: `infra/terraform/envs/ktcloud/` 활용
   - 기존 VM 운영 유지 시: 테라폼 state drift 방지를 위해 쉘 스크립트(`sh`)로 안전하게 추가

---

### b. AWS 설정 순서 (클라우드 DR & 관제)

AWS는 Terraform Provider(`hashicorp/aws`)가 완벽히 지원되므로, **인프라 규칙은 Terraform을 1순위로 적용**하고, **노드 내부 동기화 로직은 `sh` 스크립트로 추가**합니다.

1. **설정 순서**:
   - **Step 1 (Terraform 1순위)**: Security Group 및 S3 수명주기 규칙 추가
     ```bash
     cd infra/terraform/envs/aws/
     terraform init
     terraform plan   # 기존 자원 보존 및 추가 규칙만 확인
     terraform apply
     ```
   - **Step 2 (동기화 셋팅)**: `aws-dr` 인스턴스에 온프렘 `10.10.2.10` 역방향 백업 스크립트 배치
   - **Step 3 (타이머 등록)**: systemd 타이머(`aws-onprem-sync.timer`)로 1분 주기 백업 감시 데몬 등록
2. **실행 스크립트 (`sh`)**:
   ```bash
   # AWS DR(aws-dr) 인스턴스 접속 후 실행
   sudo bash scripts/setup_aws_dr_addons.sh
   ```

---

### c. 온프레미스 오픈스택 설정 순서 (OpenStack & K8s)

기존 가동 중인 OpenStack VM(`k8s-cp1`, `db-01`, `controller`)을 그대로 유지하면서, 중앙 백업 대상 권한과 K8s 트래픽 인지를 추가합니다.

1. **설정 순서**:
   - **Step 1 (Terraform 1순위 검토)**: `infra/terraform/envs/onprem`의 `terraform-provider-openstack`을 통해 보안그룹(`sg-db`, `sg-k8s`)의 내부 포트 허용 규칙 선언
   - **Step 2 (DB 백업 수신 계정)**: `db-01 (10.10.2.10)`에 접속하여 AWS 승격 쓰기 수신용 계정(`repl_backup`) 생성
     ```sql
     CREATE USER IF NOT EXISTS 'repl_backup'@'%' IDENTIFIED BY 'figteam_db_pass';
     GRANT ALL PRIVILEGES ON minwon.* TO 'repl_backup'@'%';
     FLUSH PRIVILEGES;
     ```
   - **Step 3 (K8s All-in-One 점검)**: `k8s-cp1`에서 트래픽 유입 및 WireGuard 터널 바인딩 검증
2. **실행 스크립트 (`sh`)**:
   ```bash
   # 온프레미스 마스터(controller 또는 k8s-cp1) 접속 후 실행
   sudo bash scripts/setup_onprem_openstack_addons.sh
   ```

---

## 3. 원클릭 실행 스크립트 요약표

| 대상 클라우드 | 스크립트 경로 | 설치/추가 구성요소 | 기존 설정 보존 여부 |
| :--- | :--- | :--- | :--- |
| **KT Cloud** | `scripts/setup_ktcloud_edge_addons.sh` | Nginx `geo` 판별 모듈, 업스트림 헤더 주입, 전용 로깅 | **100% 보존 (백업 후 무중단 적용)** |
| **AWS DR** | `scripts/setup_aws_dr_addons.sh` | 온프렘(10.10.2.10) 자동 백업 동기화, systemd 타이머 | **100% 보존 (K3s/MySQL 무영향)** |
| **온프레미스** | `scripts/setup_onprem_openstack_addons.sh` | db-01 백업 수신 계정, k8s-cp1 트래픽 점검 스크립트 | **100% 보존 (VM 가동 무중단 유지)** |
