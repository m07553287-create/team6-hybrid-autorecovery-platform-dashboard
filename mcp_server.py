#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FIGTEAM #cfg Model Context Protocol (MCP) Server.

figteam 하이브리드 멀티클라우드(온프렘 OpenStack · KT Cloud · AWS DR)의
실측 인프라 사양, 네트워크 토폴로지, 공통 변수, 설정 코드, 접속 자격증명 및
트러블슈팅 가이드를 AI 에이전트(Claude Code, Claude Desktop, Cursor, Antigravity 등)에
표준 MCP (JSON-RPC 2.0 / SSE / Direct HTTP / Stdio) 프로토콜로 공유합니다.

URL 엔드포인트:
  - SSE (원격 연결):    https://figteam.ktci5.kr/mcp/sse
  - HTTP RPC (단발 호출): https://figteam.ktci5.kr/mcp/rpc
  - 헬스체크:            https://figteam.ktci5.kr/mcp/healthz

실행 모드:
  - SSE / HTTP 서버: python3 mcp_server.py --port 18092
  - Stdio 모드:      python3 mcp_server.py --stdio
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any

# 루트 디렉토리 및 content 모듈 경로 추가
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR / "content"))

try:
    import settings_guide as g
except ImportError:
    # content/settings_guide.py 직접 로드 시도
    import importlib.util
    spec = importlib.util.spec_from_file_location("settings_guide", ROOT_DIR / "content" / "settings_guide.py")
    if spec and spec.loader:
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
    else:
        raise RuntimeError("settings_guide.py 모듈을 로드할 수 없습니다.")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "figteam-cfg-mcp"
SERVER_VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# Core Logic & MCP Handlers
# ---------------------------------------------------------------------------
class FigteamMcpCore:
    def __init__(self):
        self.data = g.data()
        self.variables = g.VARIABLES
        self.steps = g.STEPS
        self.pages = g.PAGES
        self.measured = g.MEASURED

    def get_topology(self) -> dict[str, Any]:
        """엔드투엔드 멀티클라우드 토폴로지 및 트래픽 경로 반환"""
        overview = self.pages.get("overview", {})
        blocks = overview.get("blocks", [])
        codes = [b.get("code") for b in blocks if b.get("type") == "code"]
        return {
            "title": "FIGTEAM 하이브리드 3사(온프렘·KT·AWS) 엔드투엔드 토폴로지",
            "measured": self.measured,
            "architecture": (
                "1. 사용자 인입: https://minwon.ktci5.kr (Cloudflare) ➔ KT Edge (14.63.212.190, Nginx WAF 10s 캐싱)\n"
                "2. 3사 메시망: WireGuard wg0 (10.200.0.1 KT Hub 51820) ↔ wg-kt (10.200.0.2 s1)\n"
                "3. 온프렘 호스트: s1 (t1-vm2 / 10.10.10.8) VIP 10.10.1.100:80 ➔ DNAT 192.168.120.226:30080\n"
                "4. VMware OpenStack: Controller(160, RAM 14GB), Compute1(161, 8GB), Compute3(163, 8GB), Compute4(164, 8GB)\n"
                "5. OpenStack PaaS/Data: k8s-cp1(172.20.0.86), k8s-w1(172.20.0.180), db-01(10.10.2.10 MySQL 8.4 Primary)\n"
                "6. AWS DR (Pilot-Light): aws-dr (10.51.1.165, MySQL Replica GTID ON), aws-ctl (10.50.1.85, Orchestrator :8080)"
            ),
            "traffic_diagram": codes[0] if len(codes) > 0 else "",
            "cloudflared_ingress": codes[1] if len(codes) > 1 else ""
        }

    def get_common_variables(self, query: str = "") -> list[dict[str, str]]:
        """공통 변수표 검색 및 조회"""
        query_lower = (query or "").lower().strip()
        results = []
        for row in self.variables:
            var_name, val, usage, check = row[0], row[1], row[2], row[3]
            if not query_lower or query_lower in var_name.lower() or query_lower in val.lower() or query_lower in usage.lower():
                results.append({
                    "variable": var_name,
                    "value": val,
                    "usage": usage,
                    "check_on_change": check
                })
        return results

    def get_instance_details(self, instance_id: str) -> dict[str, Any]:
        """특정 인스턴스 사양 및 영역 목록 조회"""
        # key 정규화: s1 -> inst-s1, controller -> inst-controller
        key = instance_id.strip().lower()
        if not key.startswith("inst-") and f"inst-{key}" in self.pages:
            key = f"inst-{key}"
        elif key == "db" or key == "db01":
            key = "inst-db01"
        elif key == "ktedge":
            key = "inst-ktedge"
        elif key == "awsdr":
            key = "inst-awsdr"
        elif key == "awsctl":
            key = "inst-awsctl"

        if key not in self.pages:
            available = [k.replace("inst-", "") for k in self.pages.keys() if k.startswith("inst-")]
            return {
                "error": f"인스턴스 '{instance_id}'를 찾을 수 없습니다.",
                "available_instances": available
            }

        p = self.pages[key]
        areas_summary = []
        for a in p.get("areas", []):
            areas_summary.append({
                "area_id": a.get("id"),
                "name": a.get("name"),
                "status": a.get("status"),
                "has_config": len(a.get("config", [])) > 0,
                "has_commands": len(a.get("commands", [])) > 0,
                "has_trouble": len(a.get("trouble", [])) > 0
            })

        return {
            "instance_id": key,
            "title": p.get("title"),
            "cloud": p.get("cloud"),
            "tag": p.get("tag"),
            "status": p.get("status"),
            "steps": p.get("steps"),
            "desc": p.get("desc"),
            "specs": p.get("specs", []),
            "areas": areas_summary
        }

    def get_area_config(self, instance_id: str, area_id: str) -> dict[str, Any]:
        """특정 인스턴스의 특정 영역 설정/명령/트러블슈팅 상세 조회"""
        key = instance_id.strip().lower()
        if not key.startswith("inst-") and f"inst-{key}" in self.pages:
            key = f"inst-{key}"
        elif key in ("db", "db01"):
            key = "inst-db01"

        if key not in self.pages:
            return {"error": f"인스턴스 '{instance_id}'를 찾을 수 없습니다."}

        p = self.pages[key]
        target_area = None
        for a in p.get("areas", []):
            if a.get("id") == area_id.strip().lower():
                target_area = a
                break

        if not target_area:
            avail = [a.get("id") for a in p.get("areas", [])]
            return {
                "error": f"인스턴스 '{key}'에 영역 '{area_id}'가 없습니다.",
                "available_areas": avail
            }

        return {
            "instance": p.get("title"),
            "area_id": target_area.get("id"),
            "area_name": target_area.get("name"),
            "status": target_area.get("status"),
            "design_principles": target_area.get("design", []),
            "config_files": target_area.get("config", []),
            "commands": target_area.get("commands", []),
            "verification": target_area.get("verify", []),
            "troubleshooting": target_area.get("trouble", [])
        }

    def get_auth_matrix(self) -> dict[str, Any]:
        """전체 접속 키 및 인증 종합 매트릭스 반환"""
        s1_access = self.get_area_config("s1", "access")
        configs = s1_access.get("config_files", [])
        matrix_code = ""
        for cfg in configs:
            if "매트릭스" in cfg.get("label", ""):
                matrix_code = cfg.get("code", "")
                break

        return {
            "title": "FIGTEAM 인프라 계층별 접속 키 및 인증 종합 매트릭스",
            "measured": self.measured,
            "principles": [
                "1. s1 물리 호스트는 단일 점프호스트(Basion)로 동작하며 팀원 개인키(~/.ssh/id_ed25519)로 진입합니다.",
                "2. OpenStack 내부 노드는 s1 root 키(/root/.ssh/id_rsa) 기반 직접 SSH 및 ~/bin/osx 래퍼로 원격 제어합니다.",
                "3. AWS 노드는 외부 22번 포트가 보안그룹으로 차단되어 반드시 s1(WG 10.200.0.2) 경유 ProxyJump 방식을 사용합니다.",
                "4. 비밀번호나 비밀키 파일은 저장소에 직접 노출하지 않고 안전한 파일 경로 및 확인 명령어로 관리합니다."
            ],
            "auth_matrix_text": matrix_code or "s1.access 영역의 종합 매트릭스를 참조하세요."
        }

    def search_troubleshooting(self, query: str) -> list[dict[str, Any]]:
        """장애 증상 및 키워드 기반 트러블슈팅 항목 검색"""
        q = (query or "").lower().strip()
        matches = []
        for pid, page in self.pages.items():
            inst_title = page.get("title", pid)
            for a in page.get("areas", []):
                area_name = a.get("name", a.get("id"))
                for tr in a.get("trouble", []):
                    symptom, cause, check_cmd, solution = tr[0], tr[1], tr[2], tr[3]
                    full_text = f"{inst_title} {area_name} {symptom} {cause} {check_cmd} {solution}".lower()
                    if not q or q in full_text:
                        matches.append({
                            "instance": inst_title,
                            "area": area_name,
                            "symptom": symptom,
                            "cause": cause,
                            "check_command": check_cmd,
                            "solution": solution
                        })
        return matches

    def get_steps_guide(self, step_no: str = "") -> list[dict[str, Any]]:
        """S0~S12 선행 순서 및 검증 게이트 조회"""
        sn = (step_no or "").upper().strip()
        results = []
        for s in self.steps:
            if not sn or s.get("no") == sn:
                results.append({
                    "step": s.get("no"),
                    "title": s.get("title"),
                    "where": s.get("where"),
                    "page": s.get("page"),
                    "area": s.get("area"),
                    "why": s.get("why"),
                    "gate": s.get("gate")
                })
        return results

    def query_config_raw(self, section: str = "") -> Any:
        """#cfg 원본 구조화 데이터 질의"""
        sec = (section or "").lower().strip()
        if sec in ("var", "vars", "variables"):
            return self.variables
        elif sec in ("step", "steps"):
            return self.steps
        elif sec in ("inst", "instances"):
            return {k: {"title": v.get("title"), "specs": v.get("specs")} for k, v in self.pages.items() if k.startswith("inst-")}
        elif sec in ("domains",):
            return g.DOMAINS
        elif sec in ("scripts",):
            return [{k: v for k, v in x.items() if k != "generate"} for x in g.SCRIPTS]
        return {
            "measured": self.measured,
            "instances": list(self.pages.keys()),
            "variables_count": len(self.variables),
            "steps_count": len(self.steps)
        }

    # -----------------------------------------------------------------------
    # JSON-RPC 2.0 Dispatcher
    # -----------------------------------------------------------------------
    def handle_rpc(self, req: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(req, dict):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}

        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        # 알림(Notification)은 응답 불필요
        if method == "notifications/initialized":
            return None

        # 1. initialize
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {}
                    },
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION
                    }
                }
            }

        # 2. ping
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        # 3. tools/list
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "get_topology",
                            "description": "온프렘(s1/OpenStack), KT Cloud, AWS DR 3사 하이브리드 멀티클라우드 전체 아키텍처 및 트래픽 경로를 조회합니다.",
                            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
                        },
                        {
                            "name": "get_common_variables",
                            "description": "S1_HOST, OS_CONTROLLER, OS_COMPUTE, FIP_CP1, CP1/W1/DB, VIP_APP 등 인프라 핵심 공통 변수 및 2026-11-27 최신 실측값을 검색/조회합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "변수명, IP, 사용처 등 필터링 검색어 (예: 'S1', '192.168', 'controller', 'RAM')"}
                                }
                            }
                        },
                        {
                            "name": "get_instance_details",
                            "description": "지정 인스턴스(s1, controller, cp1, w1, db01, ktedge, ktw1, awsdr, awsctl)의 OS/CPU/RAM/디스크/네트워크 사양 및 영역 목록을 조회합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "instance_id": {"type": "string", "description": "인스턴스 식별자 (예: 's1', 'controller', 'cp1', 'w1', 'db01', 'ktedge', 'awsdr', 'awsctl')"}
                                },
                                "required": ["instance_id"]
                            }
                        },
                        {
                            "name": "get_area_config",
                            "description": "특정 인스턴스의 세부 영역 설정 코드(config), 운영 명령어(commands), 검증 절차(verify), 트러블슈팅(trouble)을 조회합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "instance_id": {"type": "string", "description": "인스턴스 식별자 (예: 's1', 'controller', 'cp1', 'db01')"},
                                    "area_id": {"type": "string", "description": "영역 식별자 (예: 'access', 'vmnet', 'wg', 'cfd', 'svc', 'net', 'sg', 'image', 'k3s', 'mysql', 'backup')"}
                                },
                                "required": ["instance_id", "area_id"]
                            }
                        },
                        {
                            "name": "get_auth_matrix",
                            "description": "전체 인프라 계층(s1, OpenStack, K8s, DB, AWS, WireGuard, 웹 콘솔)의 접속 계정, 키 파일 위치, 권한, 프로토콜 종합 매트릭스를 반환합니다.",
                            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}
                        },
                        {
                            "name": "search_troubleshooting",
                            "description": "장애 증상 및 오류 키워드(예: 6443, Permission denied, DNS, 타임아웃, 메모리, MTU 등)로 원인 분석과 조치 명령어를 검색합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "검색할 증상이나 키워드 (예: 'ssh 타임아웃', 'Permission denied', 'DNS', '메모리', 'GTID')"}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "get_steps_guide",
                            "description": "S0부터 S12까지 인프라 구축 및 장애 복구 선행 순서, 이유, 통과 기준(Gate)을 조회합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "step_no": {"type": "string", "description": "조회할 단계 번호 (예: 'S0', 'S1' 등, 생략 시 전체 반환)"}
                                }
                            }
                        },
                        {
                            "name": "query_config_raw",
                            "description": "#cfg 사이트의 구조화된 원본 데이터를 섹션별로 질의합니다.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "section": {"type": "string", "description": "'variables', 'steps', 'instances', 'domains', 'scripts' 중 선택"}
                                }
                            }
                        }
                    ]
                }
            }

        # 4. tools/call
        if method == "tools/call":
            tool_name = params.get("name")
            args = params.get("arguments", {})
            try:
                res_content: Any = None
                if tool_name == "get_topology":
                    res_content = self.get_topology()
                elif tool_name == "get_common_variables":
                    res_content = self.get_common_variables(args.get("query", ""))
                elif tool_name == "get_instance_details":
                    res_content = self.get_instance_details(args.get("instance_id", ""))
                elif tool_name == "get_area_config":
                    res_content = self.get_area_config(args.get("instance_id", ""), args.get("area_id", ""))
                elif tool_name == "get_auth_matrix":
                    res_content = self.get_auth_matrix()
                elif tool_name == "search_troubleshooting":
                    res_content = self.search_troubleshooting(args.get("query", ""))
                elif tool_name == "get_steps_guide":
                    res_content = self.get_steps_guide(args.get("step_no", ""))
                elif tool_name == "query_config_raw":
                    res_content = self.query_config_raw(args.get("section", ""))
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"지원하지 않는 도구입니다: {tool_name}"}
                    }

                formatted_text = json.dumps(res_content, ensure_ascii=False, indent=2) if not isinstance(res_content, str) else res_content
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {"type": "text", "text": formatted_text}
                        ]
                    }
                }
            except Exception as e:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": f"도구 실행 중 오류 발생: {e}"}
                }

        # 5. resources/list
        if method == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "resources": [
                        {"uri": "figteam://config/variables", "name": "공통 변수표", "mimeType": "application/json"},
                        {"uri": "figteam://config/topology", "name": "엔드투엔드 토폴로지", "mimeType": "application/json"},
                        {"uri": "figteam://config/auth-matrix", "name": "접속 키 및 인증 매트릭스", "mimeType": "application/json"},
                        {"uri": "figteam://config/steps", "name": "선행 순서표 S0~S12", "mimeType": "application/json"},
                        {"uri": "figteam://config/instances", "name": "인스턴스 전체 요약", "mimeType": "application/json"}
                    ]
                }
            }

        # 6. resources/read
        if method == "resources/read":
            uri = params.get("uri", "")
            content_data = None
            if uri == "figteam://config/variables":
                content_data = self.get_common_variables()
            elif uri == "figteam://config/topology":
                content_data = self.get_topology()
            elif uri == "figteam://config/auth-matrix":
                content_data = self.get_auth_matrix()
            elif uri == "figteam://config/steps":
                content_data = self.get_steps_guide()
            elif uri == "figteam://config/instances":
                content_data = self.query_config_raw("instances")
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": f"알 수 없는 리소스 URI: {uri}"}
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(content_data, ensure_ascii=False, indent=2)
                        }
                    ]
                }
            }

        # 7. prompts/list
        if method == "prompts/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "prompts": [
                        {
                            "name": "troubleshoot_incident",
                            "description": "figteam 인프라 장애 발생 시 증상을 기반으로 원인 분석 및 단계별 점검/복구 명령어 안내",
                            "arguments": [{"name": "incident_description", "description": "발생한 장애 또는 오류 증상", "required": True}]
                        },
                        {
                            "name": "connect_node",
                            "description": "특정 인스턴스 또는 호스트에 올바른 인증 키와 ProxyJump 경로로 접속하는 가이드 생성",
                            "arguments": [{"name": "target_node", "description": "접속 대상 노드 (s1, cp1, w1, db-01, dr, kt-edge 등)", "required": True}]
                        },
                        {
                            "name": "daily_health_check",
                            "description": "온프렘, KT, AWS 3사 전체 인프라 1초 원라이너 헬스체크 스크립트 실행 안내",
                            "arguments": []
                        }
                    ]
                }
            }

        # 8. prompts/get
        if method == "prompts/get":
            pname = params.get("name")
            pargs = params.get("arguments", {})
            if pname == "troubleshoot_incident":
                inc = pargs.get("incident_description", "")
                matches = self.search_troubleshooting(inc)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        f"다음 인프라 장애에 대해 figteam #cfg 설정 데이터베이스를 기반으로 점검 및 복구 절차를 제시해 주세요:\n"
                                        f"장애 내용: {inc}\n\n"
                                        f"관련 트러블슈팅 데이터베이스 매칭 결과:\n"
                                        f"{json.dumps(matches, ensure_ascii=False, indent=2)}"
                                    )
                                }
                            }
                        ]
                    }
                }
            elif pname == "connect_node":
                tgt = pargs.get("target_node", "")
                matrix = self.get_auth_matrix()
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        f"노드 '{tgt}'에 접속하기 위한 SSH 명령, 점프호스트 규칙, 키 파일 위치를 안내해 주세요.\n\n"
                                        f"인증 매트릭스 정보:\n{matrix.get('auth_matrix_text')}"
                                    )
                                }
                            }
                        ]
                    }
                }
            elif pname == "daily_health_check":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": (
                                        "온프렘, KT Cloud, AWS DR 전 노드의 1초 헬스체크 명령어와 자동 루프 검증 스크립트를 실행하고 "
                                        "각 노드별 정상 출력 기준을 점검해 주세요.\n\n"
                                        "검증 명령어: for h in s1 cp1 w1 db-01 dr kt-edge; do printf '%-8s ' $h; ssh -o ConnectTimeout=8 $h hostname 2>&1 | tail -1; done"
                                    )
                                }
                            }
                        ]
                    }
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32602, "message": f"알 수 없는 프롬프트: {pname}"}
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"지원하지 않는 메서드입니다: {method}"}
        }


# ---------------------------------------------------------------------------
# HTTP & SSE Server Transport
# ---------------------------------------------------------------------------
class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class McpHttpHandler(BaseHTTPRequestHandler):
    core: FigteamMcpCore = None
    # SSE 세션: sessionId -> queue.Queue
    sessions: dict[str, queue.Queue] = {}
    sessions_lock = threading.Lock()

    def do_OPTIONS(self):
        """CORS 프리플라이트 처리"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        # 1. 헬스체크
        if path in ("/healthz", "/mcp/healthz", "/console/mcp/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            resp = {
                "status": "ok",
                "server": SERVER_NAME,
                "version": SERVER_VERSION,
                "measured": self.core.measured,
                "endpoints": {
                    "sse": "/mcp/sse",
                    "rpc": "/mcp/rpc",
                    "healthz": "/mcp/healthz"
                }
            }
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode("utf-8"))
            return

        # 2. SSE 엔드포인트: /sse, /mcp/sse, /console/mcp/sse
        if path in ("/sse", "/mcp/sse", "/console/mcp/sse"):
            session_id = str(uuid.uuid4())
            msg_queue = queue.Queue()
            with self.sessions_lock:
                self.sessions[session_id] = msg_queue

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # 첫 이벤트: 클라이언트가 POST 보낼 메시지 엔드포인트 URL 전달
            prefix = "/mcp" if "/mcp" in path else ""
            endpoint_url = f"{prefix}/messages?sessionId={session_id}"
            try:
                self.wfile.write(f"event: endpoint\ndata: {endpoint_url}\n\n".encode("utf-8"))
                self.wfile.flush()

                # SSE 메시지 펌프 루프
                while True:
                    try:
                        # 15초마다 타임아웃 걸어 킵얼라이브 ping 전송
                        item = msg_queue.get(timeout=15.0)
                        if item is None:
                            break
                        msg_str = json.dumps(item, ensure_ascii=False)
                        self.wfile.write(f"event: message\ndata: {msg_str}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        # Keep-alive ping
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                with self.sessions_lock:
                    self.sessions.pop(session_id, None)
            return

        # 기타 경로는 404
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = urllib.parse.parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            req_json = json.loads(body.decode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}).encode("utf-8"))
            return

        # 1. SSE 세션 메시지 전송 엔드포인트: /messages, /mcp/messages
        if path in ("/messages", "/mcp/messages", "/console/mcp/messages"):
            session_id = qs.get("sessionId", [None])[0]
            if not session_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"error": "Missing sessionId"}')
                return

            with self.sessions_lock:
                q = self.sessions.get(session_id)

            if not q:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"error": "Session not found"}')
                return

            # RPC 실행 후 큐에 전달
            res = self.core.handle_rpc(req_json)
            if res is not None:
                q.put(res)

            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "accepted"}')
            return

        # 2. Direct HTTP JSON-RPC 엔드포인트: /rpc, /mcp/rpc, /mcp, /
        if path in ("/rpc", "/mcp/rpc", "/mcp", "/console/mcp/rpc", "/console/mcp", "/"):
            res = self.core.handle_rpc(req_json)
            self.send_response(200 if res is not None else 204)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if res is not None:
                self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')

    def log_message(self, format, *args):
        # 표준 로깅 축약
        if "/healthz" not in self.path:
            sys.stderr.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {args[0]} {args[1]} -> {args[2]}\n")


# ---------------------------------------------------------------------------
# Stdio Loop
# ---------------------------------------------------------------------------
def run_stdio(core: FigteamMcpCore):
    """표준 입출력 (Stdio) 기반 JSON-RPC 2.0 처리기"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            res = core.handle_rpc(req)
            if res is not None:
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_res = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"}
            }
            sys.stdout.write(json.dumps(err_res, ensure_ascii=False) + "\n")
            sys.stdout.flush()


# ---------------------------------------------------------------------------
# Self-Test Function
# ---------------------------------------------------------------------------
def run_test(core: FigteamMcpCore):
    print("=== [FIGTEAM #cfg MCP Server 기능 자체 점검] ===")
    print("1. 전체 토폴로지 조회 (get_topology):")
    topo = core.get_topology()
    print(f"   제목: {topo['title']}")
    print(f"   개요: {topo['architecture'][:120]}...")

    print("\n2. 공통 변수 검색 (query='RAM'):")
    vars_res = core.get_common_variables("RAM")
    for v in vars_res:
        print(f"   - {v['variable']}: {v['value']}")

    print("\n3. 인스턴스 상세 조회 (s1):")
    inst = core.get_instance_details("s1")
    print(f"   - {inst['title']} ({inst['tag']})")
    print(f"   - 영역 목록: {[a['name'] for a in inst.get('areas', [])]}")

    print("\n4. 영역 상세 설정 조회 (s1.access):")
    area = core.get_area_config("s1", "access")
    print(f"   - 영역명: {area['area_name']}")
    print(f"   - 설정파일: {[c['label'] for c in area.get('config_files', [])]}")

    print("\n5. 트러블슈팅 검색 (query='Permission denied'):")
    tr_res = core.search_troubleshooting("Permission denied")
    for tr in tr_res:
        print(f"   - [{tr['instance']}] {tr['symptom']} ➔ 원인: {tr['cause']}")

    print("\n6. JSON-RPC initialize 테스트:")
    init_req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    init_res = core.handle_rpc(init_req)
    print("   결과:", json.dumps(init_res, ensure_ascii=False))

    print("\n7. JSON-RPC tools/list 테스트:")
    tlist_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tlist_res = core.handle_rpc(tlist_req)
    tool_names = [t["name"] for t in tlist_res["result"]["tools"]]
    print(f"   제공 도구 {len(tool_names)}종:", tool_names)

    print("\n자체 점검 통과 완료!")


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="FIGTEAM #cfg MCP Server")
    parser.add_argument("--stdio", action="store_true", help="표준 입출력(stdio) 모드로 실행")
    parser.add_argument("--http", action="store_true", help="HTTP / SSE 서버 모드로 실행")
    parser.add_argument("--port", type=int, default=18092, help="HTTP/SSE 서버 포트 (기본: 18092)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="HTTP 바인드 주소 (기본: 0.0.0.0)")
    parser.add_argument("--test", action="store_true", help="핵심 기능 자체 점검 실행")
    args = parser.parse_args()

    core = FigteamMcpCore()

    if args.test:
        run_test(core)
        return

    # 기본값: HTTP/SSE 서버 모드 (단, --stdio 가 명시적으로 주어졌을 때만 stdio)
    if args.stdio:
        run_stdio(core)
        return

    # 기본값: HTTP/SSE 서버 모드 실행
    McpHttpHandler.core = core
    server = ThreadedHTTPServer((args.host, args.port), McpHttpHandler)
    sys.stderr.write(f"====================================================\n")
    sys.stderr.write(f"🚀 FIGTEAM #cfg MCP Server 시작됨\n")
    sys.stderr.write(f"   • 주소: http://{args.host}:{args.port}\n")
    sys.stderr.write(f"   • SSE 엔드포인트: http://{args.host}:{args.port}/mcp/sse\n")
    sys.stderr.write(f"   • HTTP RPC:      http://{args.host}:{args.port}/mcp/rpc\n")
    sys.stderr.write(f"   • 헬스체크:       http://{args.host}:{args.port}/mcp/healthz\n")
    sys.stderr.write(f"   • 공개 공유 URL:  https://figteam.ktci5.kr/mcp/sse\n")
    sys.stderr.write(f"====================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n서버를 종료합니다.\n")


if __name__ == "__main__":
    main()
