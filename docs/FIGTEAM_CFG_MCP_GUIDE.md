# FIGTEAM #cfg Model Context Protocol (MCP) Server 가이드

> **엔드포인트 URL**: `https://figteam.ktci5.kr/mcp/sse`  
> **Direct HTTP RPC**: `https://figteam.ktci5.kr/mcp/rpc`  
> **상태 확인**: `https://figteam.ktci5.kr/mcp/healthz`  
> **기준 일자**: 2026-11-27 (온프렘 OpenStack RAM 증설 및 3사 실측 최신화 완료)

---

## 1. 개요 및 목적

`FIGTEAM #cfg MCP 서버`는 [figteam.ktci5.kr/#cfg](https://figteam.ktci5.kr/#cfg)에 집대성된 온프레미스(s1/VMware/OpenStack), KT Cloud Edge, AWS DR 3사 하이브리드 인프라의 **실측 변수, 접속 키 매트릭스, 네트워크 토폴로지, 설정 코드, 운영 명령어, 트러블슈팅 가이드**를 팀원들의 AI 에이전트(Claude Desktop, Cursor, Claude Code, Windsurf, Antigravity 등)가 URL 하나로 공유하고 실시간 활용할 수 있도록 제공하는 공통 자원 연동 서버입니다.

---

## 2. 클라이언트별 원클릭 연동 설정

### ① Claude Desktop (`claude_desktop_config.json`)
설정 파일 위치:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "figteam-cfg": {
      "url": "https://figteam.ktci5.kr/mcp/sse"
    }
  }
}
```

### ② Cursor / Windsurf
1. **Settings** ➔ **Features** ➔ **MCP** 메뉴로 이동합니다.
2. **Add New MCP Server** 클릭:
   - **Name**: `figteam-cfg`
   - **Type**: `SSE`
   - **Server URL**: `https://figteam.ktci5.kr/mcp/sse`
3. 연결 완료 후 녹색 불(Connected) 확인.

### ③ Claude Code (CLI)
터미널에서 아래 한 줄을 실행하면 즉시 등록됩니다:
```bash
claude mcp add --transport sse figteam-cfg https://figteam.ktci5.kr/mcp/sse
```
*(로컬 파일로 직접 stdio 연결 시: `claude mcp add figteam-cfg python3 /Users/home/projects/team6-hybrid-autorecovery-platform-dashboard/mcp_server.py --stdio`)*

### ④ REST API / 터미널 직접 호출 (curl)
SSE를 사용하지 않고 일반 HTTP POST로도 모든 도구를 직접 질의할 수 있습니다:
```bash
# 1. 헬스체크
curl -s https://figteam.ktci5.kr/mcp/healthz

# 2. 공통 변수 조회 (예: OS_CONTROLLER)
curl -s -X POST https://figteam.ktci5.kr/mcp/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "get_common_variables",
      "arguments": {"query": "OS_CONTROLLER"}
    }
  }'

# 3. 인프라 전체 접속 키 및 자격증명 매트릭스 조회
curl -s -X POST https://figteam.ktci5.kr/mcp/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "get_auth_matrix"}
  }'
```

---

## 3. 제공 도구(Tools) 상세 명세

| 도구명 (Tool) | 설명 | 주요 파라미터 |
| :--- | :--- | :--- |
| **`get_topology`** | 온프렘(s1/OpenStack), KT Cloud, AWS DR 전체 아키텍처 및 트래픽 경로 반환 | 없음 |
| **`get_common_variables`** | `S1_HOST`, `OS_CONTROLLER`, `OS_COMPUTE`, `FIP_CP1`, `VIP_APP` 등 19대 핵심 변수 실측값 검색 | `query`: 검색어 (선택) |
| **`get_instance_details`** | 특정 인스턴스(`s1`, `controller`, `cp1`, `w1`, `db01`, `ktedge`, `awsdr`, `awsctl`)의 스펙 및 영역 목록 | `instance_id`: 인스턴스명 (필수) |
| **`get_area_config`** | 특정 인스턴스 영역의 설계, 설정 코드(`config`), 운영 명령어(`commands`), 검증(`verify`), 트러블슈팅 조회 | `instance_id`, `area_id` (필수) |
| **`get_auth_matrix`** | 전체 인프라 계층(물리, OpenStack, K8s, DB, AWS, WireGuard, 웹) 접속 계정, 키 파일 경로, 권한 종합 매트릭스 | 없음 |
| **`search_troubleshooting`** | 장애 증상 및 오류 키워드(예: 6443, Permission denied, DNS, 메모리, MTU)로 해결 조치법 검색 | `query`: 증상 키워드 (필수) |
| **`get_steps_guide`** | S0~S12 선행 순서 및 검증 통과 게이트(Gate) 조회 | `step_no`: 단계 번호 (선택) |
| **`query_config_raw`** | #cfg 사이트의 구조화된 원본 데이터를 섹션별로 질의 | `section`: 섹션명 (선택) |

---

## 4. 제공 리소스(Resources)

- `figteam://config/variables` : 핵심 공통 변수표
- `figteam://config/topology` : 인프라 전체 구성도 및 트래픽 흐름
- `figteam://config/auth-matrix` : 접속 키 및 자격증명 종합 매트릭스
- `figteam://config/steps` : 선행 순서표 (S0 ~ S12)
- `figteam://config/instances` : 11대 인스턴스 전체 요약

---

## 5. 서버 아키텍처 및 운영 관리 (Host: `s1`)

```
[팀원 AI 클라이언트]
 (Claude, Cursor 등)
       │
       ▼ (HTTPS / WSS)
Cloudflare Tunnel (figteam.ktci5.kr/mcp/*)
       │
       ▼ (Local Port 18092)
s1 호스트: figteam-mcp.service (Python 3)
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

  # 실시간 로그 확인
  sudo journalctl -u figteam-mcp -f
  ```
