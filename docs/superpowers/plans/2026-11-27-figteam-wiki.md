# figteam 구성 위키 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** figteam.ktci5.kr `#cfg/` 를 팀 비밀번호로 들어가 클라우드 → 인스턴스 → 서비스 영역 문서를 만들고 고치며, 판을 비교·복구하는 구성 위키로 바꾼다.

**Architecture:** 화면은 기존 GitHub Pages(`backend/server.py` LANDING_HTML + `content/` 주입)에 두고, s1 cloudflared 의 경로 규칙 `^/api/` 로 OpenStack 전용 VM `wiki-01`(FastAPI + SQLite)에 보낸다. 화면은 `/api/tree` 를 기존 렌더러의 `CFG.data` 모양으로 바꿔(어댑터) 보는 기준 4개·매트릭스를 그대로 쓴다.

**Tech Stack:** Python 3.10(Ubuntu 22.04 기본) · FastAPI · uvicorn · SQLite(WAL) · pytest + httpx(TestClient) · node:test(화면 순수 함수) · 헤드리스 Chrome(화면 확인) · OpenStack CLI · cloudflared.

**Spec:** `docs/superpowers/specs/2026-11-27-figteam-wiki-design.md`

## Global Constraints
- 브랜치 `v3` 에서 개발. main 합치기·push 는 마지막 Task 에서 사용자 확인 후.
- wiki-01: figteam 프로젝트, figteam-net `172.20.0.50` 고정, compute4, flavor `m1.wiki`(1 vCPU / 1024MB / 10GB), image `Ubuntu-22.04`, key `s1-ktci5`, sg `sg-wiki`(tcp 8080·22 ← `192.168.120.2/32`, icmp ← `172.20.0.0/24`).
- 서버: `uvicorn wiki.app:app --host 0.0.0.0 --port 8080`, systemd `figteam-wiki`, 사용자 `wiki`, 코드 `/opt/figteam-wiki`, DB `/var/lib/figteam-wiki/wiki.db`, env `/etc/figteam-wiki/env`(600).
- 환경변수: `WIKI_DB`(DB 경로), `TEAM_CREATE_CODE`, `ALLOWED_ORIGIN`(기본 `https://figteam.ktci5.kr`), `SERVE_STATIC`(로컬 개발 때만 `public` 경로).
- 의존성은 fastapi, uvicorn, pytest, httpx 만.
- 비밀번호: `hashlib.pbkdf2_hmac('sha256', pw, salt16, 600000)`, `hmac.compare_digest`. 세션 토큰 `secrets.token_urlsafe(32)`, DB 에는 SHA-256 hex, 7일. 쿠키 `fw_s`: `HttpOnly; Secure; SameSite=Lax; Path=/api`.
- 로그인·팀 생성 실패: `slug|Cf-Connecting-Ip` 기준 10분 10회 초과 → 429.
- 상태 변경 요청 `Origin != ALLOWED_ORIGIN` → 403.
- body 64KB 초과 413, 팀당 문서 2000개 초과 422, member 1~20자, slug `^[a-z0-9-]{3,32}$`.
- kind: `cloud`(parent 없음) · `instance`(parent=cloud) · `area`(parent=instance) · `steps`(팀당 1) · `page`.
- 도메인 8개 고정: network, security, web, compute, app, data, dr, ops.
- `/api/tree` 는 `docs.current_body` 만 읽는다. 판 기록은 `revisions(doc_id, rev)` 인덱스로 해당 문서만.
- 공개 페이지에 가이드 데이터·스크립트 사본을 넣지 않는다.
- 비밀값을 커밋하지 않는다. 시드 산출물(해시 포함)은 커밋하지 않는다(`wiki/.seed/` gitignore).
- LANDING_HTML 은 비-raw 문자열 — 주입 텍스트는 `tools/build_settings.py` 의 `py_safe` 를 거친다.
- 운영 변경(OpenStack 자원 생성, s1 cloudflared, main 합치기)은 실행 직전에 계획·영향 범위를 보여 주고 확인받는다.

## Review Focus
- 두 팀원이 같은 영역을 동시에 저장 → 뒤 사람은 409 + 내 초안 ↔ 최신 판 비교(말없이 덮어쓰기 금지). → Task 3 `test_update_conflict_409`, Task 7 conflict 확인.
- 편집 중 세션 만료 → 저장 401 이어도 초안 유지, 로그인 후 다시 저장. → Task 7 `draft survives 401`.
- 실제 WG 개인키·AWS 키 붙여넣기 → 422 + 칸 이름, `<개인키>`·`$VAR` 자리표시는 통과. → Task 1 `test_find_secret_*`.
- 하위 문서가 있는 클라우드 삭제 → 422, 삭제 문서 복구 → 트리에 다시. → Task 3 `test_delete_with_children_422`, `test_restore_deleted`.
- 예전 공개 링크 `#cfg/inst/inst-awsdr/mysql` → 로그인 뒤 같은 위치. → Task 6 legacy hash 확인.

---

## File Structure
```
wiki/
  __init__.py
  app.py            FastAPI 앱 생성 create_app(), 라우트 등록, SERVE_STATIC 처리
  db.py             connect(path) -> sqlite3.Connection(WAL, foreign_keys), init_schema(conn), SCHEMA
  guard.py          DOMAINS, find_secret(value, path='body'), validate_body(kind, body)
  auth.py           hash_password, verify_password, create_team, login, logout, get_session, require_session, change_password, rate_limit
  docs.py           get_tree, create_doc, update_doc, delete_doc, list_revisions, get_revision, restore_doc, list_changes, list_scripts, get_script
  admin.py          python3 -m wiki.admin reset-password <slug>
  requirements.txt  fastapi uvicorn pytest httpx
  tests/conftest.py client fixture(임시 DB, TEAM_CREATE_CODE='test-code', ALLOWED_ORIGIN='http://testserver')
  tests/test_guard.py · test_auth.py · test_docs.py · test_seed.py
  deploy/figteam-wiki.service · deploy/cloud-init.yaml · deploy/backup.sh · deploy/install.sh
  .seed/            (gitignore)
tools/seed_wiki.py  content/settings_guide.py → wiki.db 에 figteam 팀 시드 (wiki.db 경로 인자)
content/diff.js     diffLines(), bodyToText()
content/wiki.js     api(), 로그인 화면, treeToData(), 편집기, 기록·비교
content/settings.js (수정) · content/settings.css (수정)
content/test/diff.test.mjs
tools/build_settings.py (수정) · README.md (수정)
```

---

### Task 1: 서버 골격 · 스키마 · 입력 검사

**Files:** Create `wiki/__init__.py`, `wiki/app.py`, `wiki/db.py`, `wiki/guard.py`, `wiki/requirements.txt`, `wiki/tests/conftest.py`, `wiki/tests/test_guard.py`, `wiki/.gitignore`(`.seed/`, `__pycache__/`, `.venv/`)

**Interfaces:**
- Produces: `create_app() -> FastAPI` (`GET /api/health -> {"ok": true}`); `connect(path: str) -> sqlite3.Connection`; `init_schema(conn)`; `class ApiError(Exception)(status: int, message: str, extra: dict={})` + 예외 처리기 → `{"error": message, **extra}`; `find_secret(value, path='body') -> dict|None` (`{"field": "body.config[0].code", "pattern": "wg-private-key"}`); `validate_body(kind: str, body: dict) -> None` (`ApiError(422, ..., {"field": ...})`); `DOMAINS: list[str]`.
- 스키마: 스펙 6.2 그대로(teams, sessions, login_attempts, docs[current_body 포함], revisions, scripts, 인덱스 docs_team·rev_doc).

- [ ] **Step 1: 실패하는 시험** `wiki/tests/test_guard.py`
```python
def test_find_secret_wg_key(): assert find_secret({"config":[{"code":"PrivateKey = "+"A"*43+"="}]})["field"] == "body.config[0].code"
def test_find_secret_placeholder(): assert find_secret({"code":"PrivateKey = <허브 개인키>"}) is None
def test_find_secret_env_var(): assert find_secret({"code":'MYSQL_PWD="$MYSQL_ROOT_PASSWORD"'}) is None
def test_find_secret_akia(): assert find_secret({"x":"AKIAABCDEFGHIJKLMNOP"})
def test_find_secret_pem(): assert find_secret({"x":"-----BEGIN OPENSSH PRIVATE KEY-----"})
def test_find_secret_password_value(): assert find_secret({"x":"password=hunter22"})
def test_validate_area_domain(): pytest.raises(ApiError, validate_body, "area", {"name":"x","domains":["bogus"]})
def test_validate_instance_title(): pytest.raises(ApiError, validate_body, "instance", {})
def test_validate_korean_emoji(): validate_body("cloud", {"name":"온프렘 🖥","provider":"onprem"})
def test_health(client): assert client.get("/api/health").json() == {"ok": True}
```
- [ ] **Step 2: 실패 확인** — `python3 -m venv wiki/.venv && wiki/.venv/bin/pip install -r wiki/requirements.txt && wiki/.venv/bin/pytest wiki/tests/test_guard.py -q` → FAIL(import)
- [ ] **Step 3: 구현** — 패턴: `-----BEGIN [A-Z ]*PRIVATE KEY-----`, `PrivateKey\s*=\s*[A-Za-z0-9+/]{43}=`, `AKIA[0-9A-Z]{16}`, `gh[pousr]_[A-Za-z0-9]{36}`, `(?i)(password|passwd|pwd|secret|token)\s*[:=]\s*(?![<$'"{])\S{6,}`. 필수 칸: cloud name·provider∈{onprem,openstack,kt,aws,other}; instance title; area name·domains⊆DOMAINS(1개 이상); steps items(list); page title.
- [ ] **Step 4: 통과 확인** — `wiki/.venv/bin/pytest wiki/tests -q` → 10 passed
- [ ] **Step 5: Commit** — `git add wiki && git commit -m "feat(wiki): FastAPI 골격·SQLite 스키마·비밀값/입력 검사"`

### Task 2: 팀·로그인·세션

**Files:** Create `wiki/auth.py`, `wiki/admin.py`, `wiki/tests/test_auth.py`; Modify `wiki/app.py`

**Interfaces:**
- Consumes: Task 1 `ApiError`, `connect`.
- Produces: `require_session(request) -> Session(team_id:int, slug:str, team_name:str, member:str)` (없으면 401). 라우트: `POST /api/teams {slug,name,password,member,create_code} -> 201`, `POST /api/login {slug,password,member}`, `POST /api/logout`, `GET /api/me -> {slug, team_name, member}`, `POST /api/team/password {current,new}`. 성공 시 `Set-Cookie: fw_s=…`. `python3 -m wiki.admin reset-password <slug>` (getpass 입력, 모든 세션 만료).

- [ ] **Step 1: 실패하는 시험** `wiki/tests/test_auth.py` (요청마다 `Origin: http://testserver`)
```python
def test_create_requires_code(client): assert post(client,"/api/teams",{**T, "create_code":"wrong"}).status_code == 403
def test_create_then_me(client): post(client,"/api/teams",T); assert client.get("/api/me").json()["member"] == "다운"
def test_duplicate_slug_409(client): ...
def test_login_rate_limit(client): # 틀린 비번 10회 401, 11번째 429
def test_password_hashed(client, conn): assert conn.execute("select pw_hash from teams").fetchone()[0] != T["password"]
def test_logout(client): ... # 이후 /api/me 401
def test_change_password_expires_sessions(client): ...
def test_post_without_origin_403(client): ...
def test_cookie_flags(client): assert "HttpOnly" in r.headers["set-cookie"] and "Path=/api" in r.headers["set-cookie"]
```
- [ ] **Step 2: 실패 확인** — `wiki/.venv/bin/pytest wiki/tests/test_auth.py -q` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `wiki/.venv/bin/pytest wiki/tests -q` → 전체 통과
- [ ] **Step 5: Commit** — `git commit -am "feat(wiki): 팀 생성 암호·로그인·세션·비밀번호 재설정"`

### Task 3: 문서·판 API

**Files:** Create `wiki/docs.py`, `wiki/tests/test_docs.py`; Modify `wiki/app.py`

**Interfaces:**
- Consumes: Task 1 `validate_body`·`find_secret`, Task 2 `require_session`.
- Produces (세션 팀 범위, 다른 팀 id 404):
  - `GET /api/tree -> {team:{slug,name}, docs:[{id,kind,parent_id,sort,rev,body,updated_at}]}` (deleted 제외)
  - `POST /api/docs {kind,parent_id,sort,body,message} -> 201 {id,rev:1}`
  - `PUT /api/docs/{id} {base_rev,body,message} -> {rev}` | `409 {current:{rev,body,author,created_at}}`
  - `DELETE /api/docs/{id} {base_rev,message} -> {rev}` (하위 있으면 422)
  - `GET /api/docs/{id}/revisions -> [{rev,author,message,created_at,deleted}]` (최신 먼저)
  - `GET /api/docs/{id}/revisions/{rev} -> {rev,body,deleted,author,created_at}`
  - `POST /api/docs/{id}/restore {rev,base_rev,message} -> {rev}`
  - `GET /api/changes?before=&limit=(≤100) -> [{doc_id,kind,title,rev,author,message,created_at,deleted}]`
  - `GET /api/scripts -> [{id,path,host,status,keys}]`, `GET /api/scripts/{id} -> {path,host,status,text}`
- 저장 = 한 트랜잭션: `UPDATE docs SET current_rev=?+1, current_body=? WHERE id=? AND current_rev=?` → 0행이면 409, 아니면 revisions INSERT. 제목 = body `name|title`.

- [ ] **Step 1: 실패하는 시험** `wiki/tests/test_docs.py`
```python
def test_create_tree(client): ...                 # cloud→instance→area, len(docs)==3, area.parent_id==instance.id
def test_update_rev2(client): ...
def test_update_conflict_409(client): ...         # 둘 다 base_rev 1 → 두 번째 409, current.rev==2
def test_secret_422_field(client): ...
def test_body_too_large_413(client): ...          # 65537 바이트
def test_delete_with_children_422(client): ...
def test_restore_deleted(client): ...             # delete → tree 없음 → restore(rev=1) → tree 있음, rev==3
def test_revisions_newest_first(client): ...
def test_other_team_404(client): ...
def test_changes_title_author(client): ...
def test_doc_limit_2000(client, conn): ...        # 2000개 직접 INSERT 후 생성 → 422
```
- [ ] **Step 2: 실패 확인** — `wiki/.venv/bin/pytest wiki/tests/test_docs.py -q` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `wiki/.venv/bin/pytest wiki/tests -q` → 전체 통과
- [ ] **Step 5: Commit** — `git commit -am "feat(wiki): 문서·판·충돌·복구·최근변경·스크립트 API"`

### Task 4: figteam 시드

**Files:** Create `tools/seed_wiki.py`, `wiki/tests/test_seed.py`

**Interfaces:**
- Consumes: `content/settings_guide.py` `data()`·`SCRIPTS`·`PAGES`, `content/scripts/**`, Task 1 `connect`·`init_schema`, Task 2 `hash_password`.
- Produces: `seed(db_path: str, slug: str, name: str, password: str) -> dict(counts)`; CLI `python3 tools/seed_wiki.py --db <wiki.db> --slug figteam --name "figteam (team6)"` (비밀번호 getpass). 클라우드 4(onprem/openstack/kt/aws, 인스턴스의 cloud 로 묶음), 인스턴스 9, 영역 29(domains 포함), steps 1(page/area 참조를 새 doc id 로), page 3(overview·design-kt·trouble, vars 블록은 table 로), scripts 18. rev 1, author `seed`, message `2026-11-26 실측 가이드에서 가져옴`. 같은 slug 가 있으면 중단.

- [ ] **Step 1: 실패하는 시험**
```python
def test_seed_counts(tmp_path): c = seed(str(tmp_path/"w.db"), "figteam", "figteam", "pw-123456"); assert c == {"cloud":4,"instance":9,"area":29,"steps":1,"page":3,"scripts":18}
def test_seed_login(tmp_path, client_for): # 시드 DB 로 앱 → /api/login 200 → /api/tree docs 46
def test_seed_steps_refs(tmp_path): # steps.items[*].area_id 가 모두 존재하는 area doc id
def test_seed_twice_fails(tmp_path): ...
```
- [ ] **Step 2: 실패 확인** — `wiki/.venv/bin/pytest wiki/tests/test_seed.py -q` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `wiki/.venv/bin/pytest wiki/tests -q`
- [ ] **Step 5: Commit** — `git add tools/seed_wiki.py wiki/tests/test_seed.py && git commit -m "feat(wiki): figteam 실측 가이드 시드"`

### Task 5: 비교 함수

**Files:** Create `content/diff.js`, `content/test/diff.test.mjs`

**Interfaces:**
- Produces: `diffLines(a: string[], b: string[]) -> Array<{op:'same'|'add'|'del', a?:number, b?:number, text:string}>` (LCS/Myers); `bodyToText(kind, body) -> string[]` — cloud `이름/종류/설명`; instance `제목/태그/상태/설명/사양 k: v`; area `## 기본`(이름·상태·도메인), `## 설계`(- 줄), `## 설정 / <라벨>`(코드 줄), `## 명령어 [분류] <라벨>`, `## 검증 <라벨>`(+`기대: …`), `## 오류 시 확인`(증상 | 변수 | 확인 | 조치); steps 단계별; page 블록 순서.
- 브라우저 전역 함수 + 끝에 `if (typeof module !== 'undefined') module.exports = {diffLines, bodyToText};`. 역슬래시 쓰지 않는다(split 사용).

- [ ] **Step 1: 실패하는 시험** — `identical → all same`, `one line changed → same,del,add,same`, `insert at top`, `bodyToText area order('## 기본' 이 첫 줄, '## 설계' 가 '## 설정' 앞)`, `2000-line diff < 200ms`
- [ ] **Step 2: 실패 확인** — `node --test content/test/` → FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — `node --test content/test/` → 5 pass
- [ ] **Step 5: Commit** — `git commit -m "feat(wiki): 줄 비교·문서 텍스트화"`

### Task 6: 로그인 화면 · API 데이터로 보기

**Files:** Create `content/wiki.js`; Modify `content/settings.js`, `content/settings.css`, `tools/build_settings.py`, `content/settings_guide.py`(`static_config()` 추가), `wiki/app.py`(SERVE_STATIC)

**Interfaces:**
- Consumes: Task 2·3 API, Task 5 함수.
- Produces: `api(method, path, body?) -> Promise<any>` (401 → `wikiShowLogin()` 후 reject `{status:401}`); `wikiInit()` (설정 탭 진입 시 호출); `treeToData(tree, staticCfg) -> CFG.data` — pages 키 `inst-<id>`·`page-<id>`, area id `a<id>`, `instances` 는 클라우드 sort → 인스턴스 sort, 인스턴스에 `cloud`(provider)·`cloudId`, `scripts` = `/api/scripts` 목록(`file` 대신 `id`), `default` = 첫 인스턴스 첫 영역; `static_config() -> {domains, lensDefault}` 만 `#cfg-data` 에.
- `build_settings.py`: `public/scripts` 를 만들지 않고 있으면 지움, diff.js·wiki.js 를 settings.js 앞에 주입, `assert '"pages"' not in cfg_json`.
- `cfgViewScript` 는 `api('GET','/api/scripts/'+id).text`. 인스턴스 기준 대분류는 클라우드 제목으로 묶음. 예전 해시는 sessionStorage `fw_return` 에 두고 로그인 뒤 시드 문서의 `short`·영역 이름으로 찾아 이동.
- 로그인 화면 문구: 401 "팀 주소나 비밀번호가 맞지 않습니다", 403 "팀 생성 암호가 맞지 않습니다", 409 "이미 있는 팀 주소입니다", 429 "시도가 많습니다. 10분 뒤 다시 시도하세요".

- [ ] **Step 1: 빌드** — `bash tools/build.sh` → `build ok`, `grep -c 'db-01 (MySQL Primary)' public/index.html` → 0, `test ! -d public/scripts`
- [ ] **Step 2: 로컬 통합** — 시드 DB 생성 후 `WIKI_DB=… TEAM_CREATE_CODE=dev ALLOWED_ORIGIN=http://127.0.0.1:8080 SERVE_STATIC=public wiki/.venv/bin/uvicorn wiki.app:app --port 8080` → 헤드리스 Chrome 스크린샷: ① `/#cfg/` 로그인 화면 ② 로그인 후 기본(인스턴스 기준 › s1 › 접속 경로) ③ 서비스 기준 › 보안 ④ `*.sh` 보기 창 ⑤ **legacy hash** `#cfg/inst/inst-awsdr/mysql` → 로그인 → aws-dr MySQL 영역
- [ ] **Step 3: Commit** — `git commit -am "feat(wiki): 팀 로그인 화면·API 데이터 렌더링·공개 가이드 제거"`

### Task 7: 만들기 · 편집 · 삭제

**Files:** Modify `content/wiki.js`, `content/settings.js`, `content/settings.css`

**Interfaces:**
- Consumes: Task 3 API, Task 1 패턴의 화면용 사본 `wikiFindSecret(body)`.
- Produces: `wikiCreate(kind, parentId)`, `wikiEdit(docId)`, `wikiSave(docId, body, message)`, `wikiDelete(docId)`; 초안 sessionStorage `fw_draft_<docId|new-kind-parent>`.
- 버튼: `+ 클라우드`(대분류 끝), `+ 인스턴스`(클라우드 묶음 끝), `+ 서비스 영역`(중분류 끝), `+ 단계`(진행 순서), `+ 문서`(참고), 설명 패널 `편집`·`삭제`. 빈 팀: "클라우드부터 만드세요".
- 편집 양식 스펙 6.5. 저장 버튼 "저장", 알림 "저장했습니다 (N판)". 409: "다른 팀원이 먼저 저장했습니다" + 나란히 비교 + [최신 판으로 다시 편집] [내 초안으로 저장]. 401: 초안 유지 → 로그인 → 복원. 422 비밀값: 칸 강조 + "비밀값처럼 보이는 내용은 저장할 수 없습니다. `<개인키>` 처럼 자리표시로 바꾸세요."

- [ ] **Step 1: 로컬 시나리오(헤드리스 Chrome + 주입 스크립트)** — ① 새 팀 → 빈 화면 안내 ② 클라우드→인스턴스→영역 생성, 매트릭스 점 ③ 편집 저장 → 2판 ④ **conflict** 두 세션 동시 저장 → 비교 화면 ⑤ **draft survives 401** 편집 중 로그아웃 후 저장 → 로그인 → 초안 그대로 ⑥ 비밀값 → 칸 강조 ⑦ 하위 있는 클라우드 삭제 → 안내
- [ ] **Step 2: `wiki/.venv/bin/pytest wiki/tests -q` · `node --test content/test/` 통과**
- [ ] **Step 3: Commit** — `git commit -am "feat(wiki): 만들기·편집·삭제·충돌 처리"`

### Task 8: 기록 · 비교 · 되돌리기 · 최근 변경

**Files:** Modify `content/wiki.js`, `content/settings.js`, `content/settings.css`

**Interfaces:**
- Consumes: Task 3 revisions/restore/changes, Task 5.
- Produces: `wikiHistory(docId)`, `wikiCompare(docId, revA, revB)`, `wikiRestore(docId, rev)`; 해시 `#cfg/hist/<docId>/<revA>/<revB>`.
- 설명 패널 `내용 | 기록` 탭. 판 목록(판·작성자·시각·메모·삭제 표시), 두 판 → 나란히 비교(왼쪽 옛 판·오른쪽 새 판, 추가 초록·삭제 빨강, "같은 줄 N개" 접기), `이 판으로 되돌리기`(확인 → "N판 내용으로 되돌렸습니다"). 참고에 `최근 변경`(50개씩, 더 보기, 클릭 → 그 판과 앞 판 비교).

- [ ] **Step 1: 로컬 확인** — 3번 고친 뒤 ① 기록 4판 ② 1↔4 비교 ③ 2판으로 되돌리기 → 5판 = 2판 내용 ④ 최근 변경 → 비교 ⑤ 삭제 문서가 "삭제" 로 보이고 되돌리기
- [ ] **Step 2: Commit** — `git commit -am "feat(wiki): 판 기록·나란히 비교·되돌리기·최근 변경"`

### Task 9: wiki-01 배포 · s1 경로 · 운영 문서

**Files:** Create `wiki/deploy/figteam-wiki.service`, `wiki/deploy/cloud-init.yaml`, `wiki/deploy/install.sh`, `wiki/deploy/backup.sh`; Modify `README.md`

**Interfaces:**
- Consumes: 전 Task. 각 단계 전 영향 범위를 알리고 확인받는다.

- [ ] **Step 1: OpenStack 자원** (controller) — `openstack flavor create m1.wiki --vcpus 1 --ram 1024 --disk 10` · `openstack security group create sg-wiki` + 규칙 3개 · `openstack port create wiki-01-port --network figteam-net --fixed-ip ip-address=172.20.0.50 --security-group sg-wiki` · admin rc 로 `openstack server create wiki-01 --flavor m1.wiki --image Ubuntu-22.04 --key-name s1-ktci5 --port wiki-01-port --availability-zone nova:compute4 --user-data cloud-init.yaml` → Expected: ACTIVE, s1 에서 `ssh ubuntu@172.20.0.50 hostname` → wiki-01
- [ ] **Step 2: 설치** — `install.sh`: 사용자 wiki, `/opt/figteam-wiki`(git archive v3 의 `wiki/`), venv, systemd 유닛, `/var/lib/figteam-wiki`, backup cron 03:30 → `curl -s 172.20.0.50:8080/api/health` (s1) → `{"ok":true}`
- [ ] **Step 3: 사용자** — wiki-01 `/etc/figteam-wiki/env` 에 `TEAM_CREATE_CODE` 입력, `python3 tools/seed_wiki.py --db /var/lib/figteam-wiki/wiki.db --slug figteam --name "figteam (team6)"` (figteam 비밀번호 입력) → 서비스 재시작
- [ ] **Step 4: s1 cloudflared** — `/etc/cloudflared/config.yml` 백업 → figteam 규칙 앞에 `path: ^/api/` → `http://172.20.0.50:8080` → `cloudflared tunnel ingress validate` · `ingress rule https://figteam.ktci5.kr/api/health` → 재시작 → `curl -s https://figteam.ktci5.kr/api/health` → `{"ok":true}`, `/api/me` → 401
- [ ] **Step 5: README** — 운영 절차(배포, `wiki.admin reset-password`, 생성 암호 변경, 백업·복원, 되돌리기 = s1 `/api/` 규칙 삭제) → 커밋
- [ ] **Step 6: main 합치기** — 사용자 확인 후 `git checkout main && git merge --no-ff v3` → **사용자 push** → 배포 확인(로그인 화면, figteam 로그인, 편집 1회, 비교 1회)
