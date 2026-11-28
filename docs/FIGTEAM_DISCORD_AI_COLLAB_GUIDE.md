# FIGTEAM GPT · Claude · Gemini 통합 로그인 공동목표 협업 가이드 (MCP · AI API 미사용)

> **통합 로그인 & 공동 목표 허브**: `https://figteam.ktci5.kr/api/ai/hub`  
> **인프라 단일 진실 소스(SSOT)**: `https://figteam.ktci5.kr/md/v1` (k3s flannel VXLAN · Pod CIDR `10.42.0.0/16`)  
> **공식 작업 웹 포털**: `https://figteam.ktci5.kr/#cfg/`

---

## 1. 한눈에 보는 구조: 웹 로그인 1회 → 3대 AI 공통 목표 타겟 + Discord 연동

팀원마다 ChatGPT, Claude, Gemini 중 편한 웹 또는 Windows 데스크탑 앱을 사용하더라도 **같은 공동 목표와 최신 진행상황**을 바라보고 결과를 Discord로 모으기 위한 무과금 구조입니다.

```text
[팀원 웹 로그인 (이름 · 접속키 · 비밀번호, 1회 로그인 시 쿠키 7일 유지)]
   │
   ▼  https://figteam.ktci5.kr/api/ai/hub
   ├─ 🎯 공동 목표 · 타겟 보드 (달성률, 상태 버튼: 대기/진행중/블로커/달성완료 → Discord 자동 알림)
   ├─ 🚀 3대 AI 원클릭 런처 (최신 공동목표 + 팀원현황 + 인프라기준 프롬프트 자동 복사 + 채팅창 실행)
   │    ├─ 🟢 ChatGPT (웹 / Windows 앱) ── Custom GPT OAuth 로그인 연결 시 자동 조회/저장도 가능
   │    ├─ 🟠 Claude  (웹 / Windows 앱) ── 원클릭 열기 또는 Ctrl+V 붙여넣기
   │    └─ 🔵 Gemini  (웹)              ── 원클릭 열기 + Ctrl+V 붙여넣기
   └─ 📣 진행 · 설정 공유 등록 / 1클릭 회신 링크 수신 ──▶ Redis 피드 저장 + Discord Webhook 전송
```

- **MCP 설정 0건 · AI API 비용 0원**: 서버는 LLM API를 호출하지 않습니다.
- **실측 k3s 기준 통일**: `k8s-cp1(172.20.0.86)` / `k8s-w1(172.20.0.180)` · `flannel VXLAN` · Pod CIDR `10.42.0.0/16` · Service CIDR `10.43.0.0/16`.

---

## 2. 팀원 사용 방법 (GPT · Claude · Gemini 공통)

1. **`https://figteam.ktci5.kr/api/ai/hub` 접속 및 로그인**
   - 팀 포털 좌측 팀 바의 **[팀 목표 · AI · Discord]** 버튼으로도 바로 열립니다.
   - 기존 `figteam` 계정(`사용자 이름` + `접속 키값` + `팀 비밀번호`)으로 1회 로그인하면 세션이 유지됩니다.
2. **공동 목표 타겟 확인 / 등록**
   - 상단 보드에서 현재 팀 공동 목표와 달성률(`N/M %`)을 확인합니다.
   - 필요 시 `+ 새 공동 목표 타겟 추가`로 목표를 등록하거나, 카드 아래 **[대기 / 진행중 / 블로커 / 달성완료]** 버튼을 눌러 Discord에 즉시 전파합니다.
3. **원하는 AI로 바로 시작**
   - 집중할 공동 목표를 드롭다운에서 고른 뒤 **[🟢 ChatGPT로 열기]**, **[🟠 Claude로 열기]**, **[🔵 Gemini로 열기]**, 또는 **[📋 공통 프롬프트 복사 (Windows 앱용)]**을 클릭합니다.
   - 최신 공동 목표 + 최근 팀원 공유 + 인프라 실측 기준 + 회신 링크 규칙이 자동으로 복사/전달됩니다.
4. **작업 완료 후 Discord & 목표에 반영**
   - AI가 생성해 준 `https://figteam.ktci5.kr/api/ai/hub?goal_id=...&area=...&status=...&title=...&summary=...` 링크를 클릭하면 폼이 미리 채워지며, **[🚀 Discord 공유 + 팀 로그 저장]** 한 번으로 팀 피드·목표 상태·Discord가 동시에 갱신됩니다.

---

## 3. ChatGPT (웹 · Windows 앱) Custom GPT OAuth 자동 연동 (선택 심화)

ChatGPT Custom GPT를 사용하면 복사/링크 클릭 없이 대화 안에서 `getTeamFeed` / `getTeamGoals` / `upsertTeamGoal` / `shareTeamUpdate`를 직접 호출합니다.

1. ChatGPT → **내 GPT** → **만들기** → **구성**
2. **지침(Instructions)**: 아래 4절 **[팀 공통 AI 채팅 지침]** 붙여넣기
3. **작업(Actions)** → **URL에서 가져오기**: `https://figteam.ktci5.kr/api/ai/openapi.json`
4. **인증(OAuth)** 설정:
   - **Client ID**: `figteam-ai-connector`
   - **Client Secret**: 서버 `/etc/figteam-wiki/env`의 `FIGTEAM_OAUTH_CLIENT_SECRET`
   - **Authorization URL**: `https://figteam.ktci5.kr/api/ai/oauth/authorize`
   - **Token URL**: `https://figteam.ktci5.kr/api/ai/oauth/token`
   - **Scope**: `read write`

---

## 4. 팀 공통 AI 채팅 지침 (ChatGPT · Claude · Gemini 공용 복붙 원문)

```markdown
# FIGTEAM 공동 목표 · 하이브리드 인프라 협업 지침

## 1. 단일 진실 소스(SSOT) & 작업 전 동기화
- 인프라 구조·IP·변수 기준은 `https://figteam.ktci5.kr/md/v1` 명세를 따른다.
  - k3s(v1.37.2+k3s1): cp1(172.20.0.86, FIP 192.168.120.226, NodePort 30080), w1(172.20.0.180), flannel VXLAN, Pod CIDR `10.42.0.0/16`, Service CIDR `10.43.0.0/16`.
- OAuth 커넥터(`getTeamFeed`, `getTeamGoals`)가 있으면 작업 전 반드시 호출해 공동 목표와 팀원 최근 공유를 먼저 확인한다.
- 커넥터가 없는 GPT/Claude/Gemini 채팅에서는 사용자가 허브(`https://figteam.ktci5.kr/api/ai/hub`) 또는 `[AI 프롬프트 복사]`로 붙여넣은 공동 목표·현황을 기준으로 답한다.

## 2. 안전 및 실행 원칙
- `s1` 호스트의 물리 조작·직접 명령은 안내하지 않으며, OpenStack / k3s / MySQL / KT Cloud / AWS DR 계층부터 다룬다.
- 실제 설정 변경은 AI가 실행하지 말고 `#cfg` 공식 웹 URL(`https://figteam.ktci5.kr/#cfg/inst/<노드>/<영역>`)을 제시해 `[👁️ 뷰 모드]` 확인 후 빨강색 `[✏️ 수정/변경]` 경고 가드로 진행하게 안내한다.

## 3. 타 영역 교차 확인(Cross-Check)
- OpenStack FIP / NodePort 변경 → KT Edge `upstream.conf` 및 s1 VIP DNAT 영향 확인
- MySQL(`10.10.2.10`) 변경 → AWS DR(`10.51.1.165`) GTID 복제 채널(`ch_dr`) 영향 확인
- WireGuard(`10.200.0.0/24`) / 공인 IP 변경 → `kt-edge` `wg0` 허브 및 `aws-ctl` 영향 확인

## 4. 공동 목표 & Discord 공유 회신
- 작업이 끝나면 먼저 5줄 요약(목표ID, 영역, 상태, 제목/내용, 타 영역 확인요청)을 제시한다.
- OAuth 커넥터가 있으면 사용자 승인 후 `shareTeamUpdate` 및 `upsertTeamGoal`을 호출한다.
- 커넥터가 없는 채팅창이면 반드시 아래 1클릭 회신 링크를 생성해 제공한다:
  `https://figteam.ktci5.kr/api/ai/hub?goal_id=<목표ID>&area=<영역>&status=<in_progress|done|check_needed|incident>&title=<제목>&summary=<요약>&check=<확인요청>`

## 5. 보안 금지
- Discord Webhook URL, 팀 인증키, 비밀번호, SSH 개인키, AWS 키, WireGuard PrivateKey를 평문으로 출력하거나 URL에 넣지 않는다.
```

---

## 5. 운영자 환경변수 체크리스트 (`wiki-01:/etc/figteam-wiki/env`)

```ini
FIGTEAM_DISCORD_WEBHOOK_URL=<DISCORD_WEBHOOK_URL>
FIGTEAM_DISCORD_NOTIFY_WIKI=1
FIGTEAM_OAUTH_CLIENT_ID=figteam-ai-connector
FIGTEAM_OAUTH_CLIENT_SECRET=<강한_랜덤값>
FIGTEAM_INTERNAL_KEY=figteam-sec-2026-dr
PUBLIC_BASE_URL=https://figteam.ktci5.kr
```
