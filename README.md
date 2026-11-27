# team6 · 민원불패 하이브리드 자동복구 플랫폼 — 통합 대시보드

`https://figteam.ktci5.kr` 통합 대시보드(CMP · DR 관제 콘솔 v2.0)의 소스 저장소입니다.  
화면은 **GitHub Actions → GitHub Pages**로 100% 정적 호스팅되며, 핵심 아키텍처 규격 및 인프라 가이드가 본 문서에 상세히 명시되어 있습니다.

---

## 📌 핵심 공식 규격 및 설정 가이드
> 본 프로젝트의 클라우드별 추가 설정 로드맵, 트래픽 판별안 및 원클릭 설치 스크립트는 아래 공식 문서에 정리되어 있습니다.  
> 1. 👉 **[클라우드별 추가 설정 순서 로드맵 및 스크립트 가이드 (docs/CLOUD_SETUP_ROADMAP_AND_SCRIPTS.md)](docs/CLOUD_SETUP_ROADMAP_AND_SCRIPTS.md)**  
> 2. 👉 **[하이브리드 멀티클라우드 아키텍처 규격 및 트래픽 판별 가이드 (docs/ARCHITECTURE_SPEC_AND_TRAFFIC_GUIDE.md)](docs/ARCHITECTURE_SPEC_AND_TRAFFIC_GUIDE.md)**  

### 🚀 원클릭 추가 설치 스크립트 (`scripts/`)
- **KT Cloud Edge 추가 설정**: `sudo bash scripts/setup_ktcloud_edge_addons.sh` (Nginx 트래픽 판별 모듈)
- **AWS DR 추가 설정**: `sudo bash scripts/setup_aws_dr_addons.sh` (온프렘 10.10.2.10 자동 백업 데몬)
- **온프레미스 오픈스택 추가 설정**: `sudo bash scripts/setup_onprem_openstack_addons.sh` (DB 백업 수신 계정)
- *원칙: 기존 VM 및 클러스터 설정 100% 보존 + 테라폼 1순위 적용 (IaC 지원 영역)*

---

## 1. 내부 트래픽 vs 외부 트래픽 판별 설정안

본 플랫폼은 민원 접수 외부 인터넷 요청과 클라우드 간 동기화/관제 내부 트래픽을 L3 IP 대역 및 L7 프록시 헤더를 통해 엄격히 분리·판별합니다.

| 트래픽 구분 | 인입 인터페이스 / 소스 대역 | 판별 식별자 / 주입 헤더 | 라우팅 및 보안 규칙 |
| :--- | :--- | :--- | :--- |
| **외부 트래픽 (North-South)** | 공인 IP (`14.63.212.190`), `eth0` | `X-Traffic-Type: EXTERNAL`<br/>`X-Real-IP: <사용자IP>` | • Nginx ModSecurity WAF 실시간 검사<br/>• 10초 마이크로캐시 적용<br/>• DB 직접 접근 차단 (403 Forbidden) |
| **내부 트래픽 (East-West)** | WireGuard (`wg-kt`, `wg0`), `10.200.0.0/24` | `X-Traffic-Type: INTERNAL` | • 터널 암호화(ChaCha20-Poly1305)<br/>• 온프렘 ↔ AWS 간 복제 및 관제 전용 |
| **격리 DB 백업 트래픽** | 내부 전용망 (`10.10.2.0/24`, `data-net`) | 전용 세그먼트 | • 공인 인터넷 라우팅 차단<br/>• MySQL 8.4 GTID 복제 및 백업 전용 |

### KT Cloud Edge Nginx 자동 분류 설정 (`traffic_classifier.conf`)
- `geo $remote_addr $traffic_type`: 사설망/터널망(`10.0.0.0/8`, `172.20.0.0/24`, `10.10.2.0/24`)은 `INTERNAL`, 그 외는 `EXTERNAL`로 자동 판별
- `proxy_set_header X-Traffic-Type $traffic_type;`: 백엔드 앱 및 인그레스로 판별 결과 전송
- 액세스 로그에 트래픽 유형(`type=$traffic_type`) 분리 기록 및 Prometheus 모니터링 연동

---

## 2. 각 클라우드별 추가 설치 구성요소 정의

3대 클라우드 환경별로 추가 설치 및 가동 중인 핵심 소프트웨어 컴포넌트와 역할 정의입니다.

| 클라우드 환경 | 인스턴스 / IP | 추가 설치 및 가동 구성요소 | 확정 역할 및 주요 기능 |
| :--- | :--- | :--- | :--- |
| **KT Cloud (Edge)** | `kt-edge`<br/>(`14.63.212.190`) | • **Nginx 1.24**<br/>• **ModSecurity v3 (WAF)**<br/>• **WireGuard (`wg-kt`)**<br/>• **traffic_classifier** | • 민원 접수 외부 트래픽 수신 및 TLS 1.3 암호화 종료<br/>• OWASP Core Rule Set 기반 웹 공격 차단<br/>• 내부/외부 트래픽 헤더 판별 태깅<br/>• 온프렘(터널 A) 및 AWS(터널 C) 트래픽 라우팅 |
| **온프레미스 (K8s)** | `k8s-cp1`<br/>(`172.20.0.86`) | • **K3s v1.37.2 (All-in-One)**<br/>• **Traefik Ingress**<br/>• **minwon-app (2 Replicas)**<br/>• **WireGuard Client (`wg0`)** | • 마스터 및 워커 단일 통합 노드 (4 vCPU / 6.5GB RAM)<br/>• 민원 접수 애플리케이션 안정 서빙 (`:30080 NodePort`)<br/>• 평시 `10.10.2.10` DB로 트랜잭션 기록 |
| **온프레미스 (DB)** | `db-01`<br/>(`10.10.2.10`) | • **MySQL 8.4 LTS Primary**<br/>• **Cinder 30GB 영구 볼륨**<br/>• **GTID 복제 엔진** | • 온프레미스 및 AWS 공용 중앙 백업 대상 (Backup Target)<br/>• 평시: 온프레미스 파드 데이터 보관<br/>• **AWS DR 승격 시: AWS에서 쓰기 발생 시 10.10.2.10으로 백업 수신** |
| **온프레미스 (호스트)**| `ktci5`<br/>(`10.10.10.8`) | • **cloudflared** (Cloudflare Tunnel)<br/>• **WireGuard Mesh (`wg0`, `wg-kt`)** | • 아웃바운드 0-Trust 터널 연계<br/>• 외부 인바운드 포트 차단 상태로 도메인 보안 라우팅 |
| **AWS (DR 노드)** | `aws-dr`<br/>(`10.200.0.4`) | • **K3s v1.37.2 (Dormant)**<br/>• **MySQL 8.4 Replica (RO)**<br/>• **WireGuard (`wg-kt`, `wg0`)** | • 평시 읽기 전용 대기 (Pilot-Light, t3.small)<br/>• L3 페일오버 시: `read_only=OFF`로 Primary 승격<br/>• **승격 후 신규 쓰기 트랜잭션 ➔ 온프렘 `10.10.2.10`으로 무유실 백업 전송** |
| **AWS (관제 엔진)** | `aws-ctl`<br/>(`10.200.0.3`) | • **FastAPI DR Orchestrator**<br/>• **Prometheus / Grafana / Loki**<br/>• **Ansible Playbook 엔진** | • S1(앱)/S2(DB 복제)/S3(네트워크) 3-Signal 통합 관측<br/>• L1 파드 재시작, L2 Ansible 서비스 복구, L3 KT Edge 절체 자동 통제 |

---

## 3. 저장소 디렉토리 구조

| 경로 | 내용 |
|---|---|
| `docs/ARCHITECTURE_SPEC_AND_TRAFFIC_GUIDE.md` | **[핵심 규격서]** 트래픽 판별안 및 클라우드별 구성요소 정의서 |
| `public/` | GitHub Pages 호스팅 정적 파일 (`index.html`, `CNAME`) |
| `backend/server.py` | 포털 원본 서버 코드 (로컬 및 온프렘 백업용) |
| `content/settings_guide.py` | **[설정] 화면 원본 데이터** — 인스턴스별 서비스 영역(설계·설정·명령어·검증·오류 시 확인), 선행 순서 S0~S12, 변수표 (2026-11-26 실측) |
| `content/settings.js` · `settings.css` | [설정] 화면 렌더러·스타일 (`tools/build_settings.py` 가 server.py 에 주입) |
| `tools/build.sh` | 정적 파일 문법 검사 및 `public/` 생성 빌드 스크립트 |
| `.github/workflows/deploy-pages.yml` | GitHub Pages 공식 자동 배포 워크플로우 |

---

## 4. 팀 협업 및 인프라 가이드

- [📖 하이브리드 멀티클라우드 아키텍처 규격 및 트래픽 판별 가이드](docs/ARCHITECTURE_SPEC_AND_TRAFFIC_GUIDE.md)
- [🛡️ 통합 운영 대시보드 파트별 상세 명세서](docs/dashboard-guide.md)
- [📋 KT Cloud 진입점 2인 분업 가이드 및 통합 검증서](docs/kt-cloud-edge-guide.md)
- [⚙️ OpenStack & 하이브리드 CI/CD · IaC 자동화 분석 보고서](docs/ci-cd-iac-automation-guide.md)
- [🔄 나의 오픈스택 ↔ 타 팀 VM/K8s 연결 조성안 (Plan C)](docs/plan-c-cross-team-interconnect.md)

---

## 5. 구성 위키 (`#cfg/`) 운영

설계: `docs/superpowers/specs/2026-11-27-figteam-wiki-design.md` · 계획: `docs/superpowers/plans/2026-11-27-figteam-wiki.md`

```
브라우저 → Cloudflare(figteam.ktci5.kr) → s1 cloudflared
            ├─ path ^/api/ → http://192.168.120.230:8080  (wiki-01 FIP: FastAPI + Redis, 전용 wiki-net + rt-wiki)
            └─ 그 외       → GitHub Pages (public/)
```

| 항목 | 위치 |
|---|---|
| 서버 코드 | `wiki/` (FastAPI + Redis). 시험: `wiki/.venv/bin/pytest wiki/tests -q` (fakeredis) |
| 화면 코드 | `content/wiki.js`(로그인·편집·기록), `content/diff.js`(판 비교), `content/settings.js`(보기) → `tools/build.sh` |
| wiki-01 | wiki-net 10.10.4.10 + FIP 192.168.120.230(rt-wiki, ext .203), compute4, `m1.wiki`, sg `sg-wiki`(8080·22·icmp ← 192.168.120.2). 앱·DB 망과 분리 |
| 저장소 | wiki-01 안 redis-server(127.0.0.1 전용, AOF) — db-01 MySQL 과 무관 |
| 비밀값 | `/etc/figteam-wiki/env`(`TEAM_CREATE_CODE`, `REDIS_PASSWORD`, 640 root:wiki), `/etc/redis/figteam-pass.conf` — 저장소에 없음 |

### 배포·갱신 (s1 에서)
```bash
bash wiki/deploy/install.sh ubuntu@192.168.120.230        # 코드 + Redis 설정 + venv + systemd + 백업 cron
ssh ubuntu@192.168.120.230 'sudoedit /etc/figteam-wiki/env' # TEAM_CREATE_CODE 입력(최초 1회)
ssh -t ubuntu@192.168.120.230 'cd /opt/figteam-wiki && sudo -u wiki bash -c "set -a; . /etc/figteam-wiki/env; .venv/bin/python tools/seed_wiki.py"'  # 최초 1회
ssh ubuntu@192.168.120.230 'sudo systemctl restart figteam-wiki'
```

### 자주 하는 운영 (wiki-01)
| 일 | 명령 |
|---|---|
| 팀 비밀번호 재설정 | `cd /opt/figteam-wiki && sudo -u wiki bash -c "set -a; . /etc/figteam-wiki/env; .venv/bin/python -m wiki.admin reset-password <팀주소>"` |
| 팀 생성 암호 바꾸기 | `sudoedit /etc/figteam-wiki/env` → `sudo systemctl restart figteam-wiki` |
| 백업 확인 | `ls -lt /var/backups/figteam-wiki` (매일 03:30 RDB, 14일) |
| 복원 | `sudo systemctl stop figteam-wiki redis-server && sudo cp /var/backups/figteam-wiki/wiki-<날짜>.rdb /var/lib/redis/dump.rdb && sudo rm -f /var/lib/redis/appendonly.aof* && sudo chown redis: /var/lib/redis/dump.rdb && sudo systemctl start redis-server figteam-wiki` (AOF 는 시작 후 `redis-cli BGREWRITEAOF`) |
| 되돌리기(위키 끄기) | s1 `/etc/cloudflared/config.yml` 의 `path: ^/api/` 규칙 삭제 → `sudo systemctl restart cloudflared` |
