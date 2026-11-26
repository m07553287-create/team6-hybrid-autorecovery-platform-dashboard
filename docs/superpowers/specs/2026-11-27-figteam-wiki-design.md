# figteam 구성 위키 — 설계 (2026-11-27)

## 1. 의도와 이유
figteam.ktci5.kr `#cfg/` 를 "정해진 가이드를 읽는 화면"에서 **팀이 함께 만들고 고치는 구성 위키**로 바꾼다.
팀원·수강생이 팀 비밀번호로 들어가 클라우드 → 인스턴스 → 서비스 영역(설계·설정·명령어·검증·오류 시 확인) 문서를 만들고,
고칠 때마다 판이 남아 **무엇이 언제 누구에 의해 바뀌었는지 비교**하며 배운다.

## 2. 목표 / 비목표 / 반(反)목표
**목표**
- 팀 만들기(팀 이름·주소·비밀번호), 팀 들어가기(비밀번호 + 자기 이름).
- 같은 팀 안에서 클라우드·인스턴스·서비스 영역·진행 순서·참고 문서를 추가·수정·삭제(복구 가능).
- 모든 문서는 판(revision)으로 저장. 아무 두 판을 골라 줄 단위로 나란히 비교, 옛 판으로 되돌리기, 팀 최근 변경 목록.
- 지금의 보기 틀(보는 기준 4개, 인스턴스×서비스 매트릭스, `*.sh` 보기 창)을 그대로 쓴다.
- figteam 팀에는 현재 실측 가이드를 1판으로 미리 넣는다.

**비목표**
- 실제 VM/클라우드 자원 생성(문서만 만든다).
- 개인별 비밀번호 계정, 팀 간 공유·권한 등급, 실시간 동시 편집, WYSIWYG 편집기.

**반목표 (기술적으로 돌아가도 실패)**
- 실제 비밀값(키·토큰·비밀번호)이 저장되는 것.
- s1 노트북이 꺼지면 위키가 멈추는 것.
- 두 사람이 동시에 고쳐 한쪽 내용이 말없이 사라지는 것.
- 팀 내용이 공개 저장소·공개 URL 로 새는 것.

## 3. 제약
- 화면은 GitHub Pages 정적 파일(`public/`), 원본은 `backend/server.py` LANDING_HTML + `content/` 주입(`tools/build.sh`). CI 가 빌드 결과 일치 검사.
- figteam.ktci5.kr 은 Cloudflare 프록시 → s1 cloudflared 터널 → github.io (현재 `/api/*` 는 github.io 404 라 충돌 없음).
- 저장소·사이트 공개 → 코드에 비밀값 금지.
- 위키 서버는 OpenStack 전용 VM `wiki-01`. compute 여유 RAM(2026-11-27 실측): compute1 162MB, compute3 321MB, **compute4 1939MB** → compute4 에만 배치 가능.
- 비용 우선순위(필수 제한 조건): 온프렘 > AWS > KT.
- 공개 경로는 s1 cloudflared 하나(figteam.ktci5.kr 은 이미 s1 터널) — 경로 규칙 `^/api/` 를 github 규칙 앞에 추가.
- 개발은 저장소 `team6-hybrid-autorecovery-platform-dashboard` 의 `v2` 브랜치. Pages 는 main 에서만 배포되므로 합치기 전까지 운영 화면 영향 없음.
- `functions/_middleware.js`(옛 Cloudflare Pages Functions, s1 프록시)는 현재 동작 안 함 — 건드리지 않는다.

## 4. 접근안 (선택: 전용 VM ① OpenStack wiki-01)
| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. Workers + D1 (처음 선택, 철회) | 화면은 Pages, `/api/*` 만 Worker → D1(SQLite) | 항상 켜짐, s1 무관, 팀 내용 비공개, 무료 한도 | 운영 플랫폼 하나 추가, 최초 계정 작업 |
| B. s1 figteam-portal + SQLite | 기존 Python 서버에 API | 가장 빠름 | 노트북·Wi-Fi 단일 장애점, 백업 별도 |
| C. GitHub 커밋 저장 | 편집 = 커밋 | 이력·비교 공짜 | 공개 저장소라 팀 내용 공개, 토큰 서버 필요, 충돌 처리 |

처음엔 A 를 골랐으나(2026-11-27) 사용자가 **위키 서버를 전용 VM 으로** 바꿨다. VM 후보:

| 안 | 위치·크기 | 월 비용 | 장점 | 단점 |
|---|---|---|---|---|
| **① OpenStack wiki-01 (선택)** | compute4, 1 vCPU / 1GB / 10GB | 0원 | 비용 1순위, 현 사이트(s1 터널 의존)와 같은 가용성, OpenStack 실사용 사례 | s1·Wi-Fi 정지 시 위키 정지, compute4 만 여유 |
| ② AWS EC2 t4g.micro | 2 vCPU / 1GB | 약 1만 원 | 상시 가동, s1 무관 | 비용, DR 시연 계정과 분리 설계 필요 |
| ③ KT Cloud VM | 1 vCore / 1~2GB | 가장 비쌈 | KT 허브 근처 | 비용 3순위 |

같은 코드를 나중에 ② 로 옮길 수 있게 서버는 OpenStack 에 묶이지 않게 만든다(설정은 환경변수).

## 5. 결정된 것 (사용자)
- 클라우드·인스턴스 "생성" = 위키 안 문서 생성.
- 사용자 = 팀원과 수강생.
- 계정 단위 = **팀**. 팀 비밀번호로 로그인하면 같은 팀 내용을 공유하고 누구나 추가·변경.
- 저장 = **OpenStack 전용 VM wiki-01** (Python FastAPI + SQLite).
- 개발 = 대시보드 저장소 `v2` 브랜치.
- 팀 만들기 = 사용자(관리자)가 정한 **팀 생성 암호**가 있어야 가능. 암호는 wiki-01 `/etc/figteam-wiki/env`(600, `TEAM_CREATE_CODE`)에만 — 저장소·DB 평문 금지, 사용자가 직접 입력.
- 공개 견본 없음 = **로그인해야만 보기**. 공개 페이지에서 정적 가이드 데이터(`#cfg-data`)와 `public/scripts/` 를 뺀다.

## 6. 설계

### 6.1 구성
```
브라우저 ──https──▶ Cloudflare (figteam.ktci5.kr) ──터널──▶ s1 cloudflared
                                                         ├─ path ^/api/ → http://172.20.0.50:8080  (wiki-01, uvicorn)
                                                         └─ 그 외       → https://m07553287-create.github.io (Pages)
wiki-01 (OpenStack figteam 프로젝트, figteam-net 172.20.0.50 고정, compute4, Ubuntu-22.04, key s1-ktci5)
  systemd figteam-wiki → uvicorn wiki.app:app --host 0.0.0.0 --port 8080 (사용자 wiki)
  DB /var/lib/figteam-wiki/wiki.db (SQLite WAL) · env /etc/figteam-wiki/env
  sg-wiki: 8080·22 ← 192.168.120.2/32 (s1), ICMP ← 172.20.0.0/24
```
저장소 `wiki/` : `wiki/app.py`(FastAPI 앱·라우트), `wiki/db.py`(스키마·연결), `wiki/auth.py`, `wiki/docs.py`, `wiki/guard.py`, `wiki/tests/`, `wiki/requirements.txt`(fastapi, uvicorn, pytest, httpx), `wiki/deploy/`(systemd 유닛, cloud-init, 백업 스크립트).

### 6.2 데이터 (SQLite)
```sql
teams(id INTEGER PK, slug TEXT UNIQUE, name TEXT, pw_hash TEXT, pw_salt TEXT, created_at INTEGER)
sessions(token_hash TEXT PK, team_id INTEGER, member TEXT, expires_at INTEGER)
login_attempts(key TEXT PK, count INTEGER, window_start INTEGER)        -- slug+IP 별 실패 횟수
docs(id INTEGER PK, team_id INTEGER, kind TEXT, parent_id INTEGER NULL, sort INTEGER,
     current_rev INTEGER, current_body TEXT /*현재 판 JSON 사본*/, deleted INTEGER DEFAULT 0, created_at INTEGER, updated_at INTEGER)
revisions(id INTEGER PK, doc_id INTEGER, rev INTEGER, body TEXT /*JSON*/, deleted INTEGER,
          author TEXT, message TEXT, created_at INTEGER, UNIQUE(doc_id, rev))
scripts(id INTEGER PK, team_id INTEGER, path TEXT, host TEXT, status TEXT, keys TEXT /*JSON*/, text TEXT)  -- figteam 시드 스크립트 사본
CREATE INDEX docs_team ON docs(team_id, deleted);
CREATE INDEX rev_doc ON revisions(doc_id, rev);
CREATE INDEX rev_team_time ON revisions(created_at) -- 최근 변경은 docs 조인 + team_id 조건
```

**성능 (1GB VM)**
- 화면 열기(`/api/tree`)는 `docs` 만 읽는다(`current_body`). 판 기록은 기록 탭에서 해당 문서 것만 인덱스로 읽는다.
- 모든 질의에 `team_id` 조건 + 인덱스. 팀당 문서 2,000개, body 64KB 상한.
- 추정(50명 활발 사용/일): 요청 약 1만, DB 수십 MB, 메모리 uvicorn 1 worker 약 100MB. SQLite WAL, 쓰기는 한 번에 하나라 동시 편집 충돌은 `current_rev` 조건으로 판정.
`kind` 와 `body`(JSON):
- `cloud` — `{name, provider: onprem|openstack|kt|aws|other, desc}` (parent 없음)
- `instance` — `{title, short, tag, status: live|design|nolook, desc, steps, specs: [[k,v]]}` (parent = cloud)
- `area` — `{name, status, domains: [8개 중 1개 이상], design: [..], config: [{label,code}], commands: [{cat,label,code}], verify: [{label,code,expect}], trouble: [[증상,변수,확인,조치]]}` (parent = instance)
- `steps` — `{items: [{no,title,where,why,gate,instance_id,area_id}]}` (팀당 1개)
- `page` — `{title, tag, desc, blocks: [{type: h|p|code|table, ...}]}` (참고 문서; `vars` 표는 page 의 table 로)

서비스 영역(도메인) 8개는 고정 목록(현재 `DOMAINS`). 매트릭스 행 = 인스턴스, 열 = 도메인.

### 6.3 인증·세션
- 팀 비밀번호: `hashlib.pbkdf2_hmac('sha256')`, 무작위 salt 16B, 반복 600,000. 평문 저장·로그 금지.
- 로그인 성공 → 무작위 32B 토큰, DB 에는 SHA-256 해시만 저장, 7일 만료.
  쿠키 `fw_s`: `HttpOnly; Secure; SameSite=Lax; Path=/api`.
- 이름(member)은 1~20자, 판의 작성자로 기록(인증 수단 아님 — 같은 팀 안 신뢰).
- 로그인 실패 slug+IP 기준 10분 10회 초과 시 429.
- 상태 변경 요청은 `Origin: https://figteam.ktci5.kr` 확인(CSRF, 개발 시 `ALLOWED_ORIGIN` 환경변수).
- 클라이언트 IP 는 cloudflared 가 넘기는 `Cf-Connecting-Ip` 헤더(없으면 소켓 주소).
- 팀 비밀번호 변경: 로그인한 팀원이 현재 비밀번호를 다시 입력해 변경, 기존 세션 모두 만료.

### 6.4 API (JSON, 모두 팀 범위)
```
POST   /api/teams               {slug,name,password,member,create_code}   → 세션 (create_code ≠ TEAM_CREATE_CODE 이면 403, 실패 횟수 제한)
POST   /api/login               {slug,password,member}                    → 세션
POST   /api/logout · GET /api/me
GET    /api/tree                팀의 모든 문서(메타 + 현재 판 body)
POST   /api/docs                {kind,parent_id,sort,body,message}        → rev 1
PUT    /api/docs/:id            {base_rev,body,message}                    → rev+1 | 409 {current}
DELETE /api/docs/:id            {base_rev,message}                         → 삭제 판(복구 가능)
GET    /api/docs/:id/revisions  [{rev,author,message,created_at,deleted}]
GET    /api/docs/:id/revisions/:rev → {body}
POST   /api/docs/:id/restore    {rev,base_rev,message}                     → 그 body 로 새 판
GET    /api/changes?before=&limit=  팀 최근 변경(문서 제목·판·작성자·시각)
GET    /api/scripts/:id          팀 스크립트 사본(로그인 필요) — `*.sh` 보기 창이 정적 파일 대신 이걸 쓴다
POST   /api/team/password       {current,new}
```
- **충돌**: `base_rev ≠ current_rev` 이면 409 + 최신 판. 화면은 "내 초안 ↔ 최신 판" 비교를 보여 주고 사용자가 합쳐 다시 저장. 말없이 덮어쓰지 않는다.
- **비밀값 차단**: 저장 전 body 전체 문자열 검사 → 일치 시 422 `{field, pattern}`.
  패턴: `-----BEGIN .*PRIVATE KEY-----`, `PrivateKey\s*=\s*[A-Za-z0-9+/]{43}=`, `AKIA[0-9A-Z]{16}`, `gh[pousr]_[A-Za-z0-9]{36}`,
  `(password|passwd|pwd|secret|token)\s*[:=]\s*[^\s<$'"{]{6,}`(값이 `<…>`·`$VAR` 형태면 허용). 화면에도 같은 검사를 미리 걸어 안내.
- 크기 제한: body 64KB, 팀당 문서 2,000개.
- 문서 삭제: 하위 문서가 있으면 422(먼저 하위 삭제) — 실수로 통째 사라지는 것 방지.

### 6.5 화면
- `#cfg/` 진입 시 `GET /api/me`.
  - 미로그인: **팀 들어가기**(팀 주소·비밀번호·이름) / **팀 만들기**(+ 팀 생성 암호). 가이드 내용은 보이지 않는다. 예전 공개 링크 `#cfg/...` 는 로그인 뒤 그 위치로 이어 준다.
  - 로그인: 상단에 팀 이름·내 이름·로그아웃, 데이터는 `GET /api/tree`.
- 보기 틀은 현재와 같다(인스턴스 기준 / 서비스 기준 / 진행 순서 / 참고 + 매트릭스). 인스턴스 기준 대분류 목록은 **클라우드별로 묶어** 보여 준다.
- 추가: 대분류 목록 끝 `+ 클라우드`, 클라우드 묶음 끝 `+ 인스턴스`, 중분류 목록 끝 `+ 서비스 영역`, 진행 순서 `+ 단계`, 참고 `+ 문서`.
  빈 팀은 첫 화면에 "클라우드부터 만드세요" 안내 → 클라우드 → 인스턴스 → 영역 순서로 이끈다.
- 편집: 설명 패널 오른쪽 위 `편집`. 구조화된 양식 — 이름/상태/도메인(체크박스), 설계(줄 목록), 설정·명령어·검증(라벨+코드, 줄 추가·삭제·순서), 오류 표(4칸 행). 저장 시 `변경 메모`(선택). 취소 시 초안 버림 확인.
- 기록: 설명 패널 `기록` 탭 — 판 목록(판 번호·작성자·시각·메모). 두 판 선택 → **나란히 비교**(왼쪽 옛 판, 오른쪽 새 판, 줄 단위 추가 초록·삭제 빨강·바뀐 줄 강조). `이 판으로 되돌리기`.
  비교 대상 텍스트 = body 를 정해진 순서의 사람이 읽는 텍스트로 펼친 것(예: `## 설계` 아래 `- …`, `## 설정 / <라벨>` 아래 코드 줄). 줄 비교는 LCS(Myers) 직접 구현, 외부 라이브러리 없음.
- 참고 > **최근 변경**: 팀 변경 목록, 누르면 그 판 비교로 이동.
- `*.sh` 보기 창: 스크립트 사본은 DB `scripts` 표(figteam 시드)에서 `/api/scripts/:id` 로 받는다 — 로그인한 같은 팀만. 정적 `public/scripts/` 는 지운다. 팀이 새 스크립트를 올리는 기능은 v1 에 없다(영역의 `설정` 코드 블록에 적는다).

### 6.6 초기 데이터
- `tools/seed_wiki.py`: `content/settings_guide.py` 데이터 → SQL(클라우드 4: 온프렘·OpenStack·KT·AWS, 인스턴스 9, 영역 29, steps 1, page 3) 생성.
  figteam 팀 비밀번호는 실행할 때 입력받아 해시만 SQL 에 넣고, 생성 SQL 은 커밋하지 않는다.
- 1판 작성자 `seed`, 메모 `2026-11-26 실측 가이드에서 가져옴`.

### 6.7 배포·되돌리기 (영향 범위를 단계마다 먼저 보여 주고 진행)
1. controller(figteam rc): flavor `m1.wiki`(1 vCPU, 1024MB, 10GB), sg `sg-wiki`, 포트 172.20.0.50, 서버 `wiki-01` (`--availability-zone nova:compute4` 는 admin rc).
2. wiki-01: cloud-init 로 python3-venv·sqlite3 설치, `/opt/figteam-wiki` 에 저장소 `wiki/` 배치, venv, systemd 유닛.
3. 사용자: `/etc/figteam-wiki/env` 에 `TEAM_CREATE_CODE` 입력. 시드: `python3 tools/seed_wiki.py` (figteam 비밀번호 입력) → wiki.db 생성 → 시드 SQL 삭제.
4. s1 cloudflared: ingress 에 `- hostname: figteam.ktci5.kr / path: ^/api/ / service: http://172.20.0.50:8080` 를 github 규칙 **앞에** 추가 → `cloudflared tunnel ingress validate` → 재시작.
   **영향 범위**: figteam.ktci5.kr `/api/*` 만 wiki-01 로. 다른 호스트·대시보드 영향 없음(cloudflared 재시작 순간 같은 터널 호스트들 수 초 끊김).
5. v2 브랜치 화면 확인 → main 합치기 → 사용자 push.
**백업**: wiki-01 cron 03:30 `sqlite3 wiki.db ".backup"` → `/var/backups/figteam-wiki/` 14일 보관 + rsync 로 aws-dr `/var/backups/minwon/incoming/wiki/` (aws-dr 의 S3 업로드 스크립트 추가는 별도 승인).
**되돌리기**: s1 ingress 의 `/api/` 규칙 삭제 → 재시작. 화면은 이전 커밋으로 되돌려 배포.

### 6.8 시험
- 서버: pytest + FastAPI TestClient(임시 SQLite) — 팀 만들기, 로그인 실패 제한, 문서 생성·수정·409 충돌·삭제·복구, 비밀값 422, 다른 팀 문서 접근 404.
- 맥 로컬 통합: `uvicorn wiki.app:app` 에 `SERVE_STATIC=public` 일 때만 정적 파일도 제공(운영에서는 끔).
- 화면: 비교 함수 단위 시험(node), 헤드리스 Chrome 으로 미로그인/로그인/편집/비교 화면 스크린샷.

## 7. 빌더에게 맡기는 것
- 파일 나누기 세부, 내부 함수 구조(의존성은 fastapi·uvicorn·pytest·httpx 만).
- 편집 양식의 세부 배치, 비교 화면 색·밀도(현재 대시보드 톤 유지).


## 8. 설계자 판단 (사용자 확인용)
- 비밀번호 분실: 관리자 화면 없이 운영자가 wiki-01 에서 `python3 -m wiki.admin reset-password <slug>` 로 재설정.
- 대시보드 탭의 기존 클라이언트 비밀번호(`figteam`) 게이트는 이번 범위 밖 — 그대로 둔다.
- 서비스 영역(도메인) 8개는 고정, 팀이 추가하지 못한다(v1).
- 팀 생성 암호 변경은 wiki-01 `/etc/figteam-wiki/env` 수정 후 서비스 재시작(사용자가 직접 입력).
- 로그인 화면에 예전 링크 위치를 기억해 로그인 뒤 그 문서로 이동.
