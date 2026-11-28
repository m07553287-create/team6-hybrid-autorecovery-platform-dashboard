# FIGTEAM Discord · 웹 로그인 AI 협업 가이드 (MCP 미사용 · AI API 과금 없음)

> **대상 환경**: ChatGPT (웹 / Windows 데스크탑 앱), Claude (웹 / Windows 데스크탑 앱), Gemini (웹)  
> **인프라 단일 진실 소스(SSOT)**: `https://figteam.ktci5.kr/md/v1`  
> **공식 작업 웹 포털**: `https://figteam.ktci5.kr/#cfg/`  
> **1클릭 공유 브리지**: `https://figteam.ktci5.kr/api/ai/share-ui`

---

## 1. 전체 구조: 왜 이렇게 연결하는가?

Discord **Incoming Webhook은 단방향 전송(Write) 전용**이라 채팅 이력을 다시 읽어올 수 없습니다.  
또한 별도 AI API 키 과금이나 로컬 MCP 설치 없이 **팀원 각자의 웹/Windows AI 채팅 앱**에서 서로의 설정·진행상황을 확인하고 Discord로 공유하기 위해 두 가지 무과금 접점을 제공합니다.

```text
[접점 A: ChatGPT 웹 / Windows 앱 (Custom GPT + OAuth 2.0)]
  ├─ 최초 1회: figteam 웹 로그인(이름 · 접속키 · 비밀번호)으로 커넥터 승인
  ├─ 확인(Read) : GET  /api/ai/feed   → 최신 팀 공유 + 위키 변경 이력 조회
  └─ 공유(Write): POST /api/ai/share  → 팀 피드 저장 + Discord Webhook 자동 전송

[접점 B: Claude 웹·Windows 앱 / Gemini 웹 (공통 지침 + 1클릭 브리지)]
  ├─ 확인(Read) : /md/v1 또는 포털 좌측 [AI용 현황 복사] 버튼으로 최신 상태 붙여넣기
  └─ 공유(Write): AI가 만든 https://figteam.ktci5.kr/api/ai/share-ui?... 링크 클릭
                   → 로그인 세션으로 1클릭 Discord 공유 + 팀 피드 저장
```

- **AI API 비용 0원**: 서버는 LLM을 호출하지 않으며, 인증·피드 저장·Discord Webhook 중계만 수행합니다.
- **보안 분리**: Discord Webhook URL은 서버 환경변수(`FIGTEAM_DISCORD_WEBHOOK_URL`)에만 보관하며, 채팅·코드·프롬프트에는 노출하지 않습니다.

---

## 2. ChatGPT (웹 · Windows 데스크탑 앱) OAuth 웹 로그인 커넥터 연결

ChatGPT Plus/Team(또는 Custom GPT 생성 권한)에서 **한 번만 Custom GPT를 만들어 팀 링크로 공유**하면, 모든 팀원이 자신의 ChatGPT 웹/Windows 앱에서 웹 로그인 후 바로 사용할 수 있습니다.

1. ChatGPT → **내 GPT** → **만들기(Create)** → **구성(Configure)** 이동
2. **이름**: `FIGTEAM 인프라 협업 비서`
3. **지침(Instructions)**: 아래 4절의 **[팀 공통 AI 채팅 지침]** 전체를 붙여넣습니다.
4. **작업(Actions)** → **새 작업 만들기** → **URL에서 가져오기(Import from URL)** 클릭:
   - 스키마 URL: `https://figteam.ktci5.kr/api/ai/openapi.json`
5. **인증(Authentication)** → **OAuth** 선택 후 아래 값 입력:
   - **Client ID**: `figteam-ai-connector`
   - **Client Secret**: (서버 `FIGTEAM_OAUTH_CLIENT_SECRET` 설정값 또는 미설정 시 빈값/임의값)
   - **Authorization URL**: `https://figteam.ktci5.kr/api/ai/oauth/authorize`
   - **Token URL**: `https://figteam.ktci5.kr/api/ai/oauth/token`
   - **Scope**: `read write`
6. 저장 후 ChatGPT가 보여주는 **OAuth Callback URL**(`https://chatgpt.com/aip/.../oauth/callback`)이 허용 접두사(`https://chatgpt.com/aip/`, `https://chat.openai.com/aip/`)에 포함되어 있는지 확인합니다.
7. 첫 대화에서 "팀 최근 진행상황 확인해줘"를 입력하면 `figteam.ktci5.kr` 로그인 화면이 열리고, 기존 **사용자 이름 + 접속 키값 + 팀 비밀번호**로 승인하면 연결이 완료됩니다.

---

## 3. Claude (웹 · Windows 앱) / Gemini 웹 연결 방법

Claude 웹·Windows 앱과 Gemini 웹은 외부 REST OAuth 커넥터를 직접 지원하지 않으므로, **공통 지침(Project / Skill / Gem)** 과 **웹 포털 1클릭 브리지**를 함께 사용합니다.

1. **지침 등록**:
   - **Claude 웹/Windows 앱**: Project 생성 → Project Instructions에 4절 지침 등록 (또는 `docs/skills/figteam-collab/SKILL.md` 업로드).
   - **Gemini 웹**: Gem 생성 → 지침란에 4절 지침 등록.
2. **서로 진행상황 확인(Read)**:
   - 웹 포털(`https://figteam.ktci5.kr/#cfg/`) 좌측 팀 바의 **[AI용 현황 복사]** 버튼을 누르면 최신 팀 공유 피드 + 위키 변경 이력이 마크다운으로 복사됩니다. AI 채팅창에 그대로 붙여넣어 컨텍스트를 동기화합니다.
   - 또는 `https://figteam.ktci5.kr/md/v1?key=<팀키>` 하단 `## 5. 최신 팀 진행상황 및 설정 공유` 섹션을 함께 확인합니다.
3. **Discord + 팀 피드 공유(Write)**:
   - 채팅에서 작업을 정리한 뒤 AI에게 "디스코드 공유 링크 만들어줘"라고 요청하면 `https://figteam.ktci5.kr/api/ai/share-ui?area=...&status=...&title=...&summary=...` 링크를 생성해 줍니다.
   - 링크를 클릭하고 **[🚀 Discord 공유 + 팀 로그 저장]** 버튼을 1번만 누르면 팀 피드 저장과 Discord 채널 전송이 동시에 처리됩니다.

---

## 4. 팀 공통 AI 채팅 지침 (복붙용 원문)

아래 블록 전체를 ChatGPT Custom GPT Instructions, Claude Project/Skill, Gemini Gem에 그대로 붙여넣어 사용하세요.

```markdown
# FIGTEAM 하이브리드 인프라 협업 지침

## 1. 단일 진실 소스(SSOT) & 작업 전 동기화
- 인프라 구조·IP·변수·설정 파일 기준은 `https://figteam.ktci5.kr/md/v1` 명세를 따른다.
- OAuth 커넥터(`getTeamFeed`)가 연결된 경우 질문/작업 전 반드시 `getTeamFeed`를 호출해 다른 팀원의 최근 진행상황과 위키 변경 이력을 먼저 확인한다.
- 커넥터가 없는 채팅창에서는 사용자가 붙여넣은 `[AI용 현황 복사]` 결과 또는 `/md/v1` 5절 내용을 먼저 확인하고, 없으면 붙여넣기를 안내한다.

## 2. 안전 및 실행 원칙
- `s1` 호스트의 물리 조작·직접 명령은 안내하지 않으며, 모든 설계·점검은 OpenStack / k3s / MySQL / KT Cloud / AWS DR 계층부터 다룬다.
- 실제 설정 변경은 AI가 직접 실행하지 말고 공식 웹 포털(`https://figteam.ktci5.kr/#cfg/inst/<노드>/<영역>`) 링크를 제공해 `[👁️ 뷰 모드]` 확인 후 빨강색 `[✏️ 수정/변경]` 경고 가드로 진행하도록 유도한다.

## 3. 교차 확인(Cross-Check) 규칙
- 설정 변경을 논의할 때 연쇄 영향을 반드시 먼저 점검한다:
  - OpenStack FIP / NodePort 변경 → KT Edge `upstream.conf` 및 s1 VIP DNAT 영향 확인
  - MySQL(`10.10.2.10`) 설정·계정 변경 → AWS DR(`10.51.1.165`) GTID 복제 채널(`ch_dr`) 영향 확인
  - WireGuard(`10.200.0.0/24`) 또는 공인 IP 변경 → `kt-edge` wg0 허브 및 `aws-ctl` 영향 확인

## 4. 진행·설정 공유 (Discord 연동)
- 작업 완료·설정 변경·확인 요청 시 아래 5줄 포맷으로 먼저 요약해 사용자 확인을 받는다:
  - **영역/노드**: 예) `inst-db01/mysql`
  - **상태**: `in_progress` | `done` | `check_needed` | `incident` | `info`
  - **제목**: 한 줄 요약
  - **내용**: 핵심 변경·점검 결과 (비밀값 금지)
  - **확인 요청**: 영향받는 타 영역 담당자 체크포인트
- OAuth 커넥터가 있으면 사용자 승인 후 `shareTeamUpdate`를 호출해 Discord에 공유한다.
- 커넥터가 없는 웹/Windows 채팅창이면 위 내용을 URL 인코딩한 1클릭 공유 링크를 만들어 제공한다:
  `https://figteam.ktci5.kr/api/ai/share-ui?area=<영역>&status=<상태>&title=<제목>&summary=<요약>&check=<확인요청>&cfg_url=<포털URL>`

## 5. 보안 금지
- Discord Webhook URL, 팀 인증키, 비밀번호, SSH 개인키, AWS 키, WireGuard PrivateKey를 요약·링크·공유 메시지에 절대 평문으로 포함하지 않는다.
```

---

## 5. 운영자 배포 체크리스트 (`wiki-01` & `s1`)

### ① `wiki-01 (192.168.120.230)` 환경변수 설정
`/etc/figteam-wiki/env`에 아래 항목을 추가합니다 (실제 값은 서버에만 보관하고 Git에 커밋하지 마세요):

```ini
FIGTEAM_DISCORD_WEBHOOK_URL=<DISCORD_WEBHOOK_URL>
FIGTEAM_DISCORD_NOTIFY_WIKI=1
FIGTEAM_OAUTH_CLIENT_ID=figteam-ai-connector
FIGTEAM_OAUTH_CLIENT_SECRET=<강한_랜덤값_선택>
FIGTEAM_INTERNAL_KEY=figteam-sec-2026-dr
PUBLIC_BASE_URL=https://figteam.ktci5.kr
```

### ② 코드 배포 및 서비스 재시작
1. `wiki-01` 배포: `bash wiki/deploy/install.sh ubuntu@192.168.120.230`
2. 정적 포털 빌드 & 푸시: `bash tools/build.sh` 후 `git add/commit/push` (Cloudflare Pages 자동 배포)
3. `s1` 호스트 `mcp_server.py` 동기화 및 `sudo systemctl restart figteam-mcp`

### ③ 동작 확인
- `curl -sS https://figteam.ktci5.kr/api/ai/openapi.json | head -n 20`
- `https://figteam.ktci5.kr/api/ai/share-ui` 브라우저 접속 후 테스트 공유 1건 등록 → Discord 채널 수신 확인
- `https://figteam.ktci5.kr/md/v1?key=<팀키>` 하단 `## 5. 최신 팀 진행상황 및 설정 공유` 표시 확인
