# team6 · 민원불패 하이브리드 자동복구 플랫폼 — 통합 대시보드

`https://figteam.ktci5.kr` 통합 대시보드(CMP · DR 관제 콘솔 v2.5.1)의 소스 저장소입니다.
화면은 **이 저장소 → Cloudflare Pages**로 배포되고, 로그인 · VM 전원 · Horizon SSO 같은 백엔드 요청만 **온프렘 터널**로 전달됩니다.

```
브라우저 ─▶ figteam.ktci5.kr (Cloudflare Pages · 이 저장소 main)
              ├─ /, /login, 정적 화면 ............ public/
              └─ /api/*, /sso/*, POST /login, /logout
                    └─ functions/_middleware.js ─▶ BACKEND_ORIGIN (figteam-api.ktci5.kr)
                                                     └─ minwon-tunnel ─▶ 온프렘 GPU 서버 localhost:18088 (backend/server.py)
```

같은 출처를 유지하므로 로그인 쿠키(`figteam_session`)와 Horizon SSO 쿠키(`Domain=.ktci5.kr`)가 그대로 동작합니다.

## 구조

| 경로 | 내용 |
|---|---|
| `public/` | Pages가 제공하는 화면 — **생성 결과, 직접 고치지 않음** |
| `functions/_middleware.js` | 백엔드 경로 전달 · 화면 제공 전 세션 확인 |
| `backend/server.base.py` | 운영 원본에서 비밀값만 설정 파일로 뺀 기준본 (생성 입력) |
| `backend/server.py` | 생성된 백엔드 (온프렘 배포 대상) |
| `backend/portal_config.example.json` | 서버 설정 파일 예시 (실제 파일은 저장소에 올리지 않음) |
| `theme/` | 청사진 테마 · DR 콘솔 · 2D 연결 구성도 엔진(`topo2d.js`) · 생성 스크립트 |
| `tools/build.sh` | 기준본 → `backend/server.py` + `public/` 생성, 비밀값 형태 검사 |
| `tools/sanitize.py` | 운영 원본 → 기준본 (비밀값 제거 · `/api/session` · 로그인 실패 리다이렉트) |

## 수정 · 빌드

```bash
# theme/ 또는 backend/server.base.py 수정 후
tools/build.sh          # backend/server.py, public/ 갱신
git add -A && git commit -m "..." && git push   # main 푸시 → Pages 자동 배포
```

백엔드(`backend/server.py`)가 바뀌었으면 온프렘에도 반영해야 합니다 (아래 2단계).

## 최초 연결 절차

> Cloudflare · 운영 서버 변경입니다. 순서대로 진행하고, 단계마다 확인 후 넘어갑니다.

### 1. 온프렘 설정 파일 (비밀값)
`/opt/figteam-portal/portal_config.json` — 형식은 `backend/portal_config.example.json`. 권한 `600`.
기존 `server.py`에 평문으로 있던 포털 · OpenStack 비밀번호는 **교체를 권장**합니다.

### 2. 백엔드 배포
```bash
scp backend/server.py 10.10.10.8:/tmp/server.py
ssh 10.10.10.8 'sudo cp /opt/figteam-portal/server.py /opt/figteam-portal/server.py.bak-$(date +%Y%m%d%H%M) \
  && sudo cp /tmp/server.py /opt/figteam-portal/server.py && sudo systemctl restart figteam-portal.service \
  && systemctl is-active figteam-portal.service'
```
이 시점에도 기존 `figteam.ktci5.kr`(터널 직결)은 그대로 동작해야 합니다.

### 3. Cloudflare Tunnel — 백엔드 전용 호스트명
Zero Trust → Networks → Tunnels → `minwon-tunnel` → Public Hostname 추가
- `figteam-api.ktci5.kr` → `http://localhost:18088` (기존 figteam과 같은 서비스)
- 권장: Access 애플리케이션 + 서비스 토큰으로 이 호스트명을 막고, 토큰을 Pages 환경변수에 넣음

### 4. Cloudflare Pages 프로젝트
Workers & Pages → Create → Pages → **Connect to Git** → 이 저장소
- Production branch `main` · Framework 없음 · Build command 비움 · **Build output `public`**
- 환경변수: `BACKEND_ORIGIN = https://figteam-api.ktci5.kr` (선택: `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`)
- `<프로젝트>.pages.dev`에서 로그인 · VM 목록 확인 (Horizon SSO 쿠키는 `.ktci5.kr` 전용이라 pages.dev에선 제외)

### 5. 도메인 전환
- Tunnel의 `figteam.ktci5.kr` Public Hostname 제거 → Pages 프로젝트 Custom domains에 `figteam.ktci5.kr` 추가
- **되돌리기**: Pages 커스텀 도메인 제거 → Tunnel에 `figteam.ktci5.kr → http://localhost:18088` 다시 추가

## 보안 메모
- 비밀값은 저장소에 넣지 않습니다 (`.gitignore`, `tools/build.sh` 검사).
- `origin-kt.ktci5.kr`(DNS 전용)가 KT Edge IP를 공개하고 있습니다 — Edge 443을 Cloudflare IP 대역만 허용하거나 Authenticated Origin Pulls 적용을 권장합니다.
