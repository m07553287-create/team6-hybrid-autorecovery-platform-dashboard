# 📋 OpenStack & 하이브리드 클라우드 CI/CD · IaC 자동화 아키텍처 비교 분석 보고서

> **문서 대상**: 오픈스택(OpenStack), 온프레미스 K8s, KT Cloud 환경의 인프라 및 배포 자동화  
> **핵심 주제**: Jenkins 설치가 필요한가? (Terraform · Ansible · GitHub Actions 조합 분석)  
> **문서 버전**: v1.0 (2026-11-13)

---

## 1. 결론 요약 (Executive Summary)

> **💡 핵심 결론: Jenkins(젠킨스) 중앙 서버는 별도로 설치할 필요가 없습니다.**  
> 전통적인 무거운 Jenkins 서버 대신, **[Terraform (인프라 선언) + Ansible (소프트웨어 구성) + GitHub Actions & Argo CD (배포 자동화)]**의 최신 경량 스택이 자원 효율성, 보안, 유지보수 측면에서 압도적으로 유리합니다.

| 도구 (Tool) | 서버/데몬 설치 필요 여부 | 역할 및 작동 방식 | 자원 소모 (RAM) | 우리 프로젝트 적합성 |
| :--- | :---: | :--- | :---: | :---: |
| **Jenkins** | **필수 (설치 비권장 ❌)** | 상시 구동 중앙 CI 서버, 전용 VM 필요 | 2~4 GB+ (JVM) | **비추천** (자원 낭비, 폐쇄망 보안 취약점) |
| **Terraform** | **불필요 (CLI 도구 ✅)** | OpenStack API 호출 기반 선언적 인프라 생성 | 0 MB (실행 시만) | **강력 추천** (VM·네트워크·보안그룹 IaC) |
| **Ansible** | **불필요 (Agentless ✅)** | SSH 기반 OS 설정 및 패키지 설치 자동화 | 0 MB (실행 시만) | **강력 추천** (Nginx, WireGuard, K8s 세팅) |
| **GitHub Actions** | **불필요 (클라우드 SaaS ✅)** | 코드 커밋 시 자동 빌드/테스트/검증 파이프라인 | 0 MB (클라우드 제공) | **강력 추천** (정적 웹 배포, PR 검증) |
| **Argo CD** | 선택 (K8s 내부 파드 ✅) | Git 저장소 변경 사항을 폐쇄망으로 자동 당김 (GitOps) | ~200 MB (경량) | **최적 조합** (인바운드 포트 개방 없이 자동 배포) |

---

## 2. 도구별 세부 분석 및 설치 필요성 검토

---

### ① Terraform (테라폼) — 클라우드 인프라 프로비저닝 (IaC)

* **설치 필요 여부**: **별도 서버 설치 불필요 (No Server Required)**
* **작동 원리**:
  * OpenStack의 `Nova`(컴퓨트), `Neutron`(네트워크), `Glance`(이미지), `Cinder`(볼륨) 공식 프로바이더(`terraform-provider-openstack`)를 지원합니다.
  * 엔지니어의 로컬 PC(Mac/Linux)나 CI 러너에 `terraform` 단일 바이너리만 있으면, `openrc` 환경변수(Keystone 인증)를 읽어 인스턴스와 네트워크를 코드로 즉시 생성/수정/삭제합니다.
* **장점**:
  * 상태 파일(`terraform.tfstate`)을 통해 현재 오픈스택의 실제 상태와 코드의 일치성을 보장.
  * 상시 돌아가는 데몬 프로세스가 없어 RAM 자원 소모 0.

---

### ② Ansible (앤서블) — 구성 관리 및 소프트웨어 자동화 (Configuration Management)

* **설치 필요 여부**: **에이전트/서버 설치 불필요 (Agentless Architecture)**
* **작동 원리**:
  * 대상 VM(OpenStack 인스턴스, KT Edge 등)에 별도의 Agent(데몬)를 설치할 필요가 전혀 없습니다.
  * 리눅스 표준인 **SSH 접속과 Python** 환경만 있으면 플레이북(`*.yml`)을 실행하여 Nginx 설치, WAF 설정, WireGuard 키 생성 등을 일괄 적용합니다.
* **장점**:
  * Jenkins처럼 중앙 서버가 죽어서 전체 파이프라인이 멈추는 단일 장애점(SPOF)이 없음.
  * 멱등성(Idempotency)을 보장하여 동일한 스크립트를 여러 번 실행해도 동일한 정상 상태 유지.

---

### ③ GitHub Actions — 지속적 통합 및 배포 (CI/CD)

* **설치 필요 여부**: **서버 설치 불필요 (GitHub 완전 관리형 서비스)**
* **폐쇄망 온프레미스 연동 방식**:
  * **일반적인 클라우드 배포**: GitHub의 표준 러너가 자동으로 코드 빌드 및 테스트를 수행 (우리가 현재 Cloudflare Pages를 배포하는 방식).
  * **온프레미스 오픈스택 배포 시 (2가지 선택지)**:
    1. **방식 A (Self-Hosted Runner, 선택적 설치)**:
       * 외부 인터넷에서 온프렘으로 들어오는 인바운드 방화벽을 뚫을 필요 없이, 온프렘 호스트(`10.10.10.8`)에 가벼운 깃허브 러너(`actions-runner`) 데몬 1개만 실행해 둡니다.
       * 러너가 GitHub와 아웃바운드 HTTPS로 통신하므로, 안전하게 내부 OpenStack CLI/Ansible을 실행할 수 있습니다.
    2. **방식 B (GitOps + Argo CD 연동, 가장 권장 ⭐)**:
       * GitHub Actions는 테스트 및 컨테이너 이미지 빌드/푸시만 수행합니다.
       * 온프렘 K8s 안의 **Argo CD**가 GitHub의 변경 사항을 100% 아웃바운드로 스스로 감지하여 내려받으므로, 러너 설치조차 필요 없이 완전한 폐쇄망 배포가 완성됩니다.

---

### ④ Jenkins (젠킨스) — 전통적인 중앙 CI 서버

* **설치 필요 여부**: **독립 VM 및 전용 서버 필수 설치 (비권장)**
* **단점 및 도입을 지양하는 이유**:
  1. **자원 낭비 (Resource Overhead)**: JVM 기반으로 최소 2~4GB 이상의 메모리를 상시 점유. 노트북 1대로 운영하는 온프렘 OpenStack 환경에서 큰 부담.
  2. **유지보수 부담 (Management Burden)**: 젠킨스 코어 및 수많은 플러그인의 호환성 충돌, 버전 업그레이드, 백업 관리 필요.
  3. **보안 취약점 (Security Risks)**: 오픈스택 내부망에 젠킨스 웹 콘솔(포트 8080)을 열어둘 경우 외부 공격 및 취약점 타깃 위험 증가.

---

## 3. 권장 아키텍처: Modern Serverless CI/CD & IaC 파이프라인

우리 하이브리드 플랫폼(FIGTEAM)에 최적화된 **"서버리스·에이전트리스"** 파이프라인입니다.

```
[ 개발자 코드 푸시 ]
        │
        ▼ (Git Push)
[ GitHub 저장소 ] 
        │
        ├─▶ [ GitHub Actions ] ─── 단위 테스트, 빌드 무결성 검증, 린트 검사
        │
        ├─▶ [ Terraform ] ──────── 로컬/CI에서 OpenStack API 직접 호출하여 VM·네트워크 생성
        │
        ├─▶ [ Ansible ] ────────── SSH로 인스턴스 접속하여 Nginx, WAF, WireGuard 자동 설정
        │
        └─▶ [ Argo CD (K8s 내부) ] ─ Git 저장소를 주기적으로 Pull하여 온프렘 K8s 파드 무중단 배포
```

---

## 4. 최종 결론 및 권고 사항

1. **Jenkins는 설치하지 마십시오.** 불필요한 자원 낭비와 관리 포인트만 늘어납니다.
2. **인프라 프로비저닝은 Terraform**으로 OpenStack VM을 코드로 관리하십시오.
3. **OS 설정 및 서비스 배포는 Ansible**을 통해 SSH 원격 자동화하십시오.
4. **배포 트리거는 GitHub Actions** 및 온프렘 내부 **Argo CD** 조합을 활용하십시오.
