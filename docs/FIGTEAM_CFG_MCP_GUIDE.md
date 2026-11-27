# FIGTEAM #cfg Model Context Protocol (MCP) 통합 연동 가이드

> **통합 공통 SSE 엔드포인트 URL**: `https://figteam.ktci5.kr/mcp/sse`  
> **로컬 AI 앱 직결 Grounding 게이트웨이**: `https://figteam.ktci5.kr/md/v1`  
> **ChatGPT Custom Actions 스펙**: `https://figteam.ktci5.kr/mcp/openapi.json`  
> **만능 원클릭 설치 스크립트**: `curl -sSL https://figteam.ktci5.kr/mcp/install | bash`  
> **Direct HTTP RPC**: `https://figteam.ktci5.kr/mcp/rpc`  
> **상태 점검 (Health Check)**: `https://figteam.ktci5.kr/mcp/healthz`  
> **기준 일자**: 2026-11-27 (온프렘 OpenStack RAM 증설 및 3사 실측 최신화 완료)

---

## 1. 개요: 5대 AI 생태계 단일 링크 통합

`FIGTEAM #cfg MCP 서버`는 [figteam.ktci5.kr/#cfg](https://figteam.ktci5.kr/#cfg)에 집대성된 온프레미스(s1/VMware/OpenStack), KT Cloud Edge, AWS DR 3사 하이브리드 인프라의 **실측 변수, 접속 키 매트릭스, 네트워크 토폴로지, 설정 코드, 운영 명령어, 트러블슈팅 가이드**를 팀원 누구나 단 하나의 링크(`https://figteam.ktci5.kr/mcp/sse`)로 연동하여 공통 자원으로 활용할 수 있도록 개통되었습니다.

지원 클라이언트:
- **Claude** (Claude Desktop, Claude Code)
- **GPT** (ChatGPT Custom GPTs / Actions, Codex CLI)
- **AGY** (Google Antigravity CLI / IDE)
- **Cursor / Windsurf** (VS Code MCP 확장 포함)
- **Gemini** (Gemini CLI, Gemini Code Assist)

---

## 2. 초간편 만능 원클릭 연동 (Universal Installer)

터미널에서 아래 단 한 줄의 명령어를 실행하면, 로컬 PC에 설치된 모든 AI 도구(Claude, Cursor, AGY, Gemini, Codex)의 설정을 자동으로 감지하여 `figteam-cfg` 서버를 즉시 등록합니다:

```bash
curl -sSL https://figteam.ktci5.kr/mcp/install | bash
```

---

## 3. 클라이언트별 단일 링크 연동 방법

### ① Claude Desktop (`claude_desktop_config.json`)
설정 파일 위치:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "figteam-cfg": {
      "url": "https://figteam.ktci5.kr/mcp/sse"
    }
  }
}
```

### ② Claude Code (CLI)
터미널에서 명령어 한 줄 실행:
```bash
claude mcp add --transport sse figteam-cfg https://figteam.ktci5.kr/mcp/sse
```

### ③ Cursor / Windsurf
1. **Settings** ➔ **Features** ➔ **MCP** 메뉴로 이동합니다.
2. **Add New MCP Server** 클릭:
   - **Name**: `figteam-cfg`
   - **Type**: `SSE`
   - **Server URL**: `https://figteam.ktci5.kr/mcp/sse`
3. 또는 전역 설정 파일(`~/.cursor/mcp.json`)에 아래 블록 추가:
   ```json
   {
     "mcpServers": {
       "figteam-cfg": {
         "url": "https://figteam.ktci5.kr/mcp/sse"
       }
     }
   }
   ```

### ④ Google Antigravity (AGY CLI / IDE)
터미널에서 명령어 한 줄 실행:
```bash
agy mcp add figteam-cfg https://figteam.ktci5.kr/mcp/sse
```

### ⑤ Gemini CLI (`settings.json`)
터미널에서 명령어 한 줄 실행:
```bash
gemini mcp add figteam-cfg https://figteam.ktci5.kr/mcp/sse
```
또는 전역 설정(`~/.gemini/settings.json`)의 `mcpServers` 블록에 추가:
```json
{
  "mcpServers": {
    "figteam-cfg": {
      "url": "https://figteam.ktci5.kr/mcp/sse"
    }
  }
}
```

### ⑥ ChatGPT & GPTs (OpenAI Custom Actions)
ChatGPT 웹에서 나만의 GPT(Custom GPT) 생성 시:
1. **Configure** ➔ **Create new action** 클릭
2. **Schema** 항목의 **[Import from URL]** 버튼 클릭
3. 아래 OpenAPI 스키마 URL 입력 후 **Import**:
   👉 `https://figteam.ktci5.kr/mcp/openapi.json`
4. 8대 도구가 자동으로 REST API 액션으로 변환되어 ChatGPT 대화창에서 즉시 실시간 인프라 데이터를 조회합니다.

### ⑦ Codex / OpenAI Agents CLI
`~/.codex/config.json` 설정 파일에 등록:
```json
{
  "mcpServers": {
    "figteam-cfg": {
      "url": "https://figteam.ktci5.kr/mcp/sse"
    }
  }
}
```

### ⑧ 로컬 AI 앱 (Chatbox, NextChat, Cursor, Continue, LibreChat 등) 직결 Grounding 게이트웨이

로컬 PC의 임의의 AI 채팅 앱에서 **OpenAI API Base URL**을 아래 단 한 줄로 설정하면, 어떤 복잡한 툴 설정 없이도 모든 대화가 **최신 인프라 실측 사실(Ground Truth)에 자동 융합(Hook)**되어 답변됩니다:

* **API Base URL**: `https://figteam.ktci5.kr/md/v1`
* **API Key**: 보유하신 OpenAI / Gemini / Groq 키 (또는 임의의 문자열 `figteam`)
* **Model**: `figteam-fact-grounded` 또는 `gpt-4o` 등 자유 선택

#### 동작 흐름 및 절대 보안 원칙:
1. **사용자 질의 입력**: 팀원이 로컬 앱에서 "DB 장애 났어", "컨트롤러 RAM 상태 어때?" 등 질문.
2. **Hook 인터셉터 자동 융합**: 요청이 들어오는 즉시 게이트웨이가 최신 실측 인프라 사양(DB IP, 포트, GTID 상태, Controller 14GB 증설 사양, 접속 키 매트릭스)을 시스템 프롬프트 최상단에 자동 융합(Prepend).
3. **읽기 전용 사실 기반 응답(Read-Only Fact-Based Advice)**: AI는 실시간 사실만을 기반으로 정밀한 원인 분석과 조언을 생성합니다.
4. **웹 콘솔 직접 실행 유도(보안 필수 원칙)**:
   * 보안상 AI를 통한 원격 명령어 대리 실행이나 설정 변경은 원천 차단됩니다.
   * 실제 모든 설정 변경, 서비스 재시작, DB 복구 명령어 실행은 **웹 포털([https://figteam.ktci5.kr/#cfg/](https://figteam.ktci5.kr/#cfg/))의 해당 인스턴스 화면으로 이동하여 안전 가드가 장착된 터미널 러너(`▶ 실행`)로 직접 수행하도록 유도**합니다.
   * 예: DB 설정은 `https://figteam.ktci5.kr/#cfg/inst/inst-db01/data` 링크 제공.

---

## 4. MCP 서버가 제공하는 8대 도구(Tools)

| 도구명 (Tool) | 설명 및 제공 정보 | 주요 파라미터 |
| :--- | :--- | :--- |
| **`get_topology`** | 온프렘(s1/OpenStack), KT Cloud, AWS DR 3사 하이브리드 전체 아키텍처 및 트래픽 경로 반환 | 없음 |
| **`get_common_variables`** | `S1_HOST`, `OS_CONTROLLER`, `OS_COMPUTE`, `FIP_CP1`, `VIP_APP` 등 19대 핵심 변수 실측값 검색 | `query`: 검색어 (선택) |
| **`get_instance_details`** | 지정 인스턴스(`s1`, `controller`, `cp1`, `w1`, `db01`, `ktedge`, `awsdr`, `awsctl`) 스펙 및 서비스 목록 | `instance_id`: 인스턴스명 (필수) |
| **`get_area_config`** | 영역별 상세 설계, 설정 코드(`config`), 운영 명령어(`commands`), 검증(`verify`), 트러블슈팅 조회 | `instance_id`, `area_id` (필수) |
| **`get_auth_matrix`** | 전체 인프라 계층(물리, OpenStack, K8s, DB, AWS, WireGuard, 웹) 접속 계정, 키 경로, 권한 매트릭스 | 없음 |
| **`search_troubleshooting`** | 장애 증상/키워드(6443, Permission denied, DNS, 메모리, MTU) 기반 원인 및 해결 조치법 검색 | `query`: 증상 키워드 (필수) |
| **`get_steps_guide`** | S0~S12 인프라 구축 및 장애 복구 선행 순서와 통과 기준(Gate) 조회 | `step_no`: 단계 번호 (선택) |
| **`query_config_raw`** | #cfg 사이트의 구조화된 원본 데이터를 섹션별로 질의 | `section`: 섹션명 (선택) |

---

## 5. 제공 리소스(Resources) & 프롬프트(Prompts)

### 리소스 (URI)
- `figteam://config/variables` : 핵심 공통 변수표
- `figteam://config/topology` : 인프라 전체 구성도 및 트래픽 흐름
- `figteam://config/auth-matrix` : 접속 키 및 자격증명 종합 매트릭스
- `figteam://config/steps` : 선행 순서표 (S0 ~ S12)
- `figteam://config/instances` : 11대 인스턴스 전체 요약

### 프롬프트 (Prompts)
- `troubleshoot_incident` : 장애 상황 입력 시 #cfg DB 기반 원인 진단 및 복구 명령 템플릿 생성
- `connect_node` : 노드명 입력 시 SSH 키 위치, ProxyJump 경로, 접속 명령어 자동 완성
- `daily_health_check` : 온프렘, KT, AWS 3사 전체 인프라 1초 원라이너 헬스체크 스크립트 실행 안내

---

## 6. 인프라 배포 및 운영 아키텍처 (Host: `s1`)

```
[팀원 AI 클라이언트]
 (Claude · GPT · AGY · Cursor · Gemini)
       │
       ▼ (HTTPS / WSS / SSE / REST)
Cloudflare Tunnel (https://figteam.ktci5.kr/mcp/*)
       │
       ▼ (Local Port 18092)
s1 호스트: figteam-mcp.service (Python 3)
       ├─ /mcp/sse          (SSE 스트리밍)
       ├─ /mcp/rpc          (Direct JSON-RPC 2.0)
       ├─ /mcp/openapi.json (ChatGPT Custom Actions)
       ├─ /mcp/mcp.json     (공통 MCP Manifest)
       ├─ /mcp/install      (만능 원클릭 설치 스크립트)
       └─ /mcp/api/*        (직결 REST API)
       │
       ▼
content/settings_guide.py (최신 실측 데이터베이스)
```

- **서비스 관리 명령어 (s1 호스트)**:
  ```bash
  # 서비스 상태 확인
  sudo systemctl status figteam-mcp

  # 서비스 재시작
  sudo systemctl restart figteam-mcp

  # 실시간 로그 모니터링
  sudo journalctl -u figteam-mcp -f
  ```
