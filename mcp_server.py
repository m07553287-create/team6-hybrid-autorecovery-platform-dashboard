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

        # 1. 헬스체크 및 개요
        if path in ("/healthz", "/mcp/healthz", "/console/mcp/healthz", "/mcp", "/mcp/"):
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
                    "healthz": "/mcp/healthz",
                    "mcp_json": "/mcp/mcp.json",
                    "openapi_json": "/mcp/openapi.json",
                    "installer": "/mcp/install",
                    "rest_api": "/mcp/api",
                    "openai_gateway": "/md/v1",
                    "context_markdown": "/md/context.md"
                },
                "one_click_setup": {
                    "claude_code": "claude mcp add --transport sse figteam-cfg https://figteam.ktci5.kr/mcp/sse",
                    "agy": "agy mcp add figteam-cfg https://figteam.ktci5.kr/mcp/sse",
                    "gemini": "gemini mcp add figteam-cfg https://figteam.ktci5.kr/mcp/sse",
                    "universal_installer": "curl -sSL https://figteam.ktci5.kr/mcp/install | bash",
                    "openai_base_url": "https://figteam.ktci5.kr/md/v1"
                }
            }
            self.wfile.write(json.dumps(resp, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        # 1-1. 웹 현황 구조 및 설계 총람 마크다운 서빙 (/md, /md/v1, /md/inst/*)
        if path in ("/md", "/md/", "/md/v1", "/md/v1/") or path.startswith("/md/v1/inst/") or path.startswith("/md/inst/") or (path.startswith("/md/") and not path.startswith("/md/v1/chat") and not path.startswith("/md/v1/models")):
            # 특정 인스턴스 지정 여부 파악
            target_inst = ""
            for prefix in ("/md/v1/inst/", "/md/inst/", "/md/v1/", "/md/"):
                if path.startswith(prefix) and path != prefix:
                    candidate = path[len(prefix):].strip("/").lower()
                    if candidate and candidate not in ("v1", "chat", "models", "context.md"):
                        target_inst = candidate
                        break

            if target_inst:
                md_content = self.build_instance_markdown(target_inst)
            else:
                md_content = self.build_web_structure_markdown()

            accept_header = self.headers.get("Accept", "")
            # 브라우저 직접 방문 시 깔끔한 다크모드 HTML 뷰어로 서빙
            if "text/html" in accept_header and "curl" not in self.headers.get("User-Agent", "").lower():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                html_resp = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FIGTEAM #cfg 인프라 현황 구조 및 웹 설정 직결 명세</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.0/github-markdown-dark.min.css">
  <style>
    body {{
      background: #0d1117;
      color: #c9d1d9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      padding: 30px 15px;
      margin: 0;
    }}
    .container {{
      max-width: 1080px;
      margin: 0 auto;
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 32px;
    }}
    pre {{ background: #0d1117 !important; border: 1px solid #30363d; border-radius: 6px; padding: 14px; overflow-x: auto; }}
    code {{ color: #79c0ff; }}
    a {{ color: #58a6ff; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .web-btn {{
      display: inline-block;
      background: #238636;
      color: #fff !important;
      padding: 4px 10px;
      border-radius: 4px;
      font-size: 13px;
      font-weight: bold;
      margin-left: 6px;
    }}
  </style>
</head>
<body class="markdown-body">
  <div class="container">
    <div style="margin-bottom: 20px; padding: 12px 16px; background: #1f2937; border-left: 4px solid #38bdf8; border-radius: 4px;">
      <strong>💡 안내:</strong> 본 문서는 <a href="https://figteam.ktci5.kr/#cfg/" target="_blank">https://figteam.ktci5.kr/#cfg/</a> 웹의 실측 현황과 설계 내용을 기반으로 생성된 마크다운 지식 소스입니다. AI는 이를 읽고 사실 기반 조언을 제공하며, 실제 입력·설정 변경은 아래 각 웹 화면에 직접 접속하여 수행합니다.
    </div>
    <pre style="white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; line-height: 1.6;">{md_content}</pre>
  </div>
</body>
</html>"""
                self.wfile.write(html_resp.encode("utf-8"))
                return

            # curl / AI Agent / 일반 텍스트 요청 시 순수 마크다운 반환
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(md_content.encode("utf-8"))
            return

        # 1-2. OpenAI 호환 모델 목록 조회 (/md/v1/models)
        if path in ("/md/v1/models", "/md/models"):
            self.handle_md_models()
            return

        # 1-3. 순수 마크다운 시스템 컨텍스트 (/md/context.md)
        if path in ("/md/context.md", "/context.md", "/mcp/context.md"):
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            md_content = self.build_grounding_context()
            self.wfile.write(md_content.encode("utf-8"))
            return

        # 2. 공통 MCP 설정 JSON (Universal mcp.json)
        if path in ("/mcp.json", "/mcp/mcp.json", "/.well-known/mcp.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            mcp_cfg = {
                "$schema": "https://json.schemastore.org/mcp.json",
                "mcpServers": {
                    "figteam-cfg": {
                        "url": "https://figteam.ktci5.kr/mcp/sse"
                    }
                }
            }
            self.wfile.write(json.dumps(mcp_cfg, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        # 3. ChatGPT Actions / Custom GPTs 전용 OpenAPI 3.1.0 스펙
        if path in ("/openapi.json", "/mcp/openapi.json", "/mcp/api/openapi.json"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            openapi_spec = self.get_openapi_spec()
            self.wfile.write(json.dumps(openapi_spec, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        # 4. 원클릭 만능 설치 스크립트 (curl -sSL https://figteam.ktci5.kr/mcp/install | bash)
        if path in ("/install", "/mcp/install", "/install.sh", "/mcp/install.sh", "/setup.sh", "/mcp/setup.sh"):
            self.send_response(200)
            self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            installer_sh = self.get_installer_script()
            self.wfile.write(installer_sh.encode("utf-8"))
            return

        # 5. ChatGPT 및 일반 REST 클라이언트 전용 직결 REST API (/mcp/api/*)
        if path.startswith("/mcp/api/") or path.startswith("/api/"):
            subpath = path.replace("/mcp/api/", "").replace("/api/", "").strip("/")
            qs = urllib.parse.parse_qs(parsed.query)
            self.handle_rest_api(subpath, qs)
            return

        # 6. SSE 엔드포인트: /sse, /mcp/sse, /console/mcp/sse
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

        # 3. OpenAI 호환 실측 Grounding Chat Completions 엔드포인트: /md/v1/chat/completions
        if path in ("/md/v1/chat/completions", "/md/chat/completions"):
            self.handle_md_chat_completions(req_json)
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"error": "Not Found"}')

    def build_web_structure_markdown(self) -> str:
        """웹(#cfg)의 사실기반 해석 기초, 방향성 및 웹 명령어 등록 가이드 총람"""
        lines = []
        lines.append("# FIGTEAM 하이브리드 인프라 (#cfg) 사실기반 해석 기초 및 웹 등록 가이드\n")
        lines.append(f"> **실측 일자**: {self.core.measured} (온프렘 OpenStack Controller 14GB 증설 / Compute 8GB 균등 증설 완료)")
        lines.append("> **작업 대상 공식 웹 포털**: https://figteam.ktci5.kr/#cfg/")
        lines.append("> **💡 핵심 정의**: 본 사이트(`https://figteam.ktci5.kr/md/v1`)는 **AI의 임의 개입 없이, 인프라의 실측 사실과 설계 해석 기초, 그리고 엔지니어가 나아갈 방향성을 사용자에게 알려주는 길(내비게이션 이정표)**입니다. 실제 모든 설정 입력, 신규 명령어 등록, 인프라 조작은 **사용자가 웹 포털([https://figteam.ktci5.kr/#cfg/](https://figteam.ktci5.kr/#cfg/))에 직접 접속하여 해당 화면에서 수행**합니다.\n")
        lines.append("---\n")

        lines.append("## 🛠️ [작업 매뉴얼] 웹 포털(#cfg)에서 명령어 추가 및 설정 등록하는 방법\n")
        lines.append("사용자가 공식 웹 사이트 [https://figteam.ktci5.kr/#cfg/](https://figteam.ktci5.kr/#cfg/) 에 접속하여 각 인프라 위치에 명령어를 등록하고 실행하는 구체적인 4단계 방법입니다:\n")

        lines.append("### 1단계: 웹 포털 접속 및 대상 위치(인스턴스) 화면 이동")
        lines.append("- 브라우저로 [https://figteam.ktci5.kr/#cfg/](https://figteam.ktci5.kr/#cfg/) 에 접속합니다.")
        lines.append("- 좌측 사이드바에서 작업을 수행할 대상 인스턴스(예: `OpenStack controller`, `k8s-cp1`, `db-01`, `kt-edge` 등)와 관리 영역(Area)을 클릭하여 해당 화면으로 이동합니다.\n")

        lines.append("### 2단계: 기존 명령어 즉시 실행 및 실시간 터미널 러너 열기")
        lines.append("- 각 설정 코드 및 명령어 블록 우측의 **`▶ 실행`** 버튼을 클릭합니다.")
        lines.append("- 클릭 즉시 화면 하단에 **푸터 닥(Taskbar)**이 생성되며, 대상 노드로 웹소켓 SSH 터널이 자동 연결된 **플로팅 윈도우 터미널**이 열립니다.")
        lines.append("- 블록의 명령어가 해당 노드로 자동 전송되어 실행 결과가 실시간으로 화면에 스트리밍됩니다.\n")

        lines.append("### 3단계: 사용자 신규 명령어 추가 및 직접 입력 (등록)")
        lines.append("- **새로운 명령어 추가 실행**: 열려 있는 플로팅 터미널 창에서 일반 터미널과 동일하게 키보드로 원하는 리눅스/쿠버네티스/MySQL 명령어를 직접 타이핑하여 실행합니다.")
        lines.append("- **창 조작 및 다중 세션 관리**: 터미널 윈도우는 마우스로 타이틀바를 드래그하여 이동하거나 우측 하단을 잡아 크기(Resize)를 자유롭게 조절할 수 있습니다. 하단 닥(Dock)에서 세션을 최소화/복원할 수 있습니다.")
        lines.append("- **작업 상태 영속화**: 다른 인스턴스 메뉴로 이동하거나 브라우저를 새로고침(F5)해도 터미널 세션과 작업 이력이 그대로 유지됩니다 (`localStorage` 영속화).\n")

        lines.append("### 4단계: 파괴적 명령에 대한 안전 가드 (Safety Guard) 확인")
        lines.append("- 서비스 중지(`stop`), 재시작(`restart`), 프로세스 종료(`kill`), 데이터 삭제(`drop`, `delete`) 등 위험 명령은 주황색 **`⚠️ 실행`** 버튼으로 자동 분류되어 표시됩니다.")
        lines.append("- 운영 실수를 방지하기 위해 확인 모달(Modal) 창이 나타나며, 사용자가 확인을 클릭해야만 최종 실행됩니다.\n")
        lines.append("---\n")

        lines.append("## 2. 인프라 사실기반 해석 기초 및 작업 방향성 요약 (2대 축)\n")
        lines.append("현재 인프라는 **[물리 베이스 게이트웨이 s1]**과 **[하이브리드 클라우드 클러스터 (s1 제외 전체)]**의 2대 축으로 설계되어 있습니다.\n")
        lines.append("| 구분 | 실측 사양 및 해석 기초 | 작업 방향성 (해석 지침) | 실제 접속하여 명령 추가할 웹 URL |")
        lines.append("| :--- | :--- | :--- | :--- |")
        lines.append("| **① s1 온프렘 호스트**<br/>*(물리 게이트웨이)* | • 20 vCPU / 30GB RAM (NVMe swap 8GB)<br/>• 단일 점프호스트(Bastion), vmnet8 NAT<br/>• WireGuard `wg-kt` (10.200.0.2) | 겉(메뉴)에서는 정돈되어 있으나 백엔드 게이트웨이로 상시 가동. 내부 VM 및 터널 점검 시 접속 | 👉 [https://figteam.ktci5.kr/#cfg/inst/inst-s1/access](https://figteam.ktci5.kr/#cfg/inst/inst-s1/access) |")
        lines.append("| **② 하이브리드 클러스터**<br/>*(s1 제외 전체 인프라)* | • **IaaS**: OpenStack Controller 14GB 증설, Compute 8GB 증설<br/>• **PaaS**: K8s cp1(172.20.0.86), w1(172.20.0.180)<br/>• **Data**: db-01(10.10.2.10) ↔ aws-dr(10.51.1.165) GTID<br/>• **Edge**: KT Edge(14.63.212.190, WAF 10s 캐싱)<br/>• **DR**: AWS Pilot-Light & 오케스트레이터 | 제어 노드(Controller)는 메모리 14GB 안정권이므로 신규 VM은 반드시 8GB 연산 노드로 스케줄링. DB 복제는 GTID 실시간 동기화 유지 | 👉 [https://figteam.ktci5.kr/#cfg/overview](https://figteam.ktci5.kr/#cfg/overview) |")
        lines.append("\n---\n")

        lines.append("## 3. 서브시스템별 사실기반 해석 기초 및 해당 위치 등록 링크\n")

        lines.append("### (1) OpenStack IaaS 제어 및 연산 계층")
        lines.append("- **해석 기초**: Controller(`192.168.120.160`)는 RAM 14GB로 증설되어 Keystone, Nova, Neutron, OVN, RabbitMQ, MariaDB 제어 부하를 안정적으로 수용합니다 (가용 8.3GB, 38%). Compute 1·3·4 노드는 각 8GB RAM으로 균등 증설되었습니다.")
        lines.append("- **작업 방향성**: 신규 인스턴스 배포 및 네트워크 포트 추가는 Controller의 OVN 가상 라우터(`172.20.0.0/24`)에 바인딩하십시오.")
        lines.append("👉 **명령 추가 위치 (웹 콘솔)**: [https://figteam.ktci5.kr/#cfg/inst/inst-controller/svc](https://figteam.ktci5.kr/#cfg/inst/inst-controller/svc) (연산: [inst-compute1](https://figteam.ktci5.kr/#cfg/inst/inst-compute1/compute))\n")

        lines.append("### (2) Kubernetes (k3s) PaaS 컨테이너 계층")
        lines.append("- **해석 기초**: Control Plane cp1(`172.20.0.86`, FIP `192.168.120.226`, VIP `10.10.1.100:80`), Worker w1(`172.20.0.180`, Calico CNI).")
        lines.append("- **작업 방향성**: 외부 인입 트래픽은 VIP 10.10.1.100:80 ➔ DNAT 192.168.120.226:30080(NodePort)으로 연결되므로 서비스 노출 시 NodePort 30080 규칙을 준수하십시오.")
        lines.append("👉 **명령 추가 위치 (웹 콘솔)**: [https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s](https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s) (워커: [inst-w1](https://figteam.ktci5.kr/#cfg/inst/inst-w1/agent))\n")

        lines.append("### (3) MySQL 8.4 데이터 및 복제 계층")
        lines.append("- **해석 기초**: Primary DB(`10.10.2.10:3306`, MySQL 8.4 LTS, GTID ON, ROW binlog) ↔ AWS DR(`10.51.1.165:3306`, Replica Pilot-Light).")
        lines.append("- **작업 방향성**: 스키마 변경 시 GTID consistency를 준수해야 하며, 사용자 계정 추가 시 `172.20.0.%`(앱 대역) 권한을 명시하십시오.")
        lines.append("👉 **명령 추가 위치 (웹 콘솔)**: [https://figteam.ktci5.kr/#cfg/inst/inst-db01/mysql](https://figteam.ktci5.kr/#cfg/inst/inst-db01/mysql) (DR복제: [inst-awsdr](https://figteam.ktci5.kr/#cfg/inst/inst-awsdr/mysql))\n")

        lines.append("### (4) KT Cloud Edge & 인입 WAF 계층")
        lines.append("- **해석 기초**: 공인 IP `14.63.212.190`, Nginx WAF 10초 마이크로캐싱, 3사 메시 WireGuard 허브(`10.200.0.1:51820`).")
        lines.append("- **작업 방향성**: WAF 룰 변경 및 업스트림 헬스체크는 Nginx 설정 블록에서 직접 수행하십시오.")
        lines.append("👉 **명령 추가 위치 (웹 콘솔)**: [https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/nginx](https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/nginx)\n")

        lines.append("### (5) AWS DR Pilot-Light 및 복구 오케스트레이터 계층")
        lines.append("- **해석 기초**: 복구 오케스트레이터 `aws-ctl (10.50.1.85:8080)`가 3사 상태를 모니터링하며 자동 승격을 준비합니다.")
        lines.append("- **작업 방향성**: DR 모의훈련 및 수동 페일오버 테스트는 오케스트레이터 API 화면에서 진행하십시오.")
        lines.append("👉 **명령 추가 위치 (웹 콘솔)**: [https://figteam.ktci5.kr/#cfg/inst/inst-awsctl/api](https://figteam.ktci5.kr/#cfg/inst/inst-awsctl/api)\n")
        lines.append("---\n")

        lines.append("## 4. 직결 마크다운 URL 일람\n")
        lines.append("- **해석 기초 및 등록 가이드 총람**: `https://figteam.ktci5.kr/md/v1`")
        lines.append("- **[블록 ①] s1 단독 명세**: `https://figteam.ktci5.kr/md/v1/s1`")
        lines.append("- **[블록 ②] 클러스터 통합 명세**: `https://figteam.ktci5.kr/md/v1/cluster`")

        return "\n".join(lines)

    def build_cluster_unified_markdown(self) -> str:
        """s1을 제외한 전체 하이브리드 멀티클라우드 클러스터 통합 명세 및 웹 설정 직결 마크다운"""
        lines = []
        lines.append("# [하이브리드 클라우드 클러스터] 통합 현황 구조 및 웹 설정 명세 총람\n")
        lines.append(f"> **실측 일자**: {self.core.measured} (Controller 14GB / Compute 8GB 증설 완료)")
        lines.append("> **포괄 범위**: s1 호스트를 제외한 온프렘 OpenStack, K8s PaaS, DB 데이터, KT Edge, AWS DR 전체 클러스터")
        lines.append("> **공식 웹 포털**: https://figteam.ktci5.kr/#cfg/overview\n")
        lines.append("---\n")

        lines.append("## 1. 5대 서브시스템 통합 현황 및 사용자 직접 설정 웹 URL\n")

        subsystems = [
            {
                "title": "MySQL 8.4 Primary & DR 복제 데이터 계층",
                "inst": "inst-db01",
                "summary": "온프렘 Primary db-01(10.10.2.10:3306) ↔ AWS DR aws-dr(10.51.1.165:3306) GTID Auto-Position 복제",
                "areas": [("MySQL 설정 및 복제", "mysql", "https://figteam.ktci5.kr/#cfg/inst/inst-db01/mysql"),
                          ("백업 및 덤프 절차", "backup", "https://figteam.ktci5.kr/#cfg/inst/inst-db01/backup")]
            },
            {
                "title": "OpenStack IaaS 제어 및 연산 계층",
                "inst": "inst-controller",
                "summary": "Controller(192.168.120.160, RAM 14GB 증설, 4GB Swap), Compute 1·3·4 (전 노드 8GB 균등 증설)",
                "areas": [("Controller 코어 서비스", "svc", "https://figteam.ktci5.kr/#cfg/inst/inst-controller/svc"),
                          ("가상 네트워크 OVN/OVS", "net", "https://figteam.ktci5.kr/#cfg/inst/inst-controller/net"),
                          ("보안 그룹 (Security Groups)", "sg", "https://figteam.ktci5.kr/#cfg/inst/inst-controller/sg"),
                          ("Compute 1·3·4 연산 노드", "compute", "https://figteam.ktci5.kr/#cfg/inst/inst-compute1/compute")]
            },
            {
                "title": "Kubernetes (k3s) PaaS 컨테이너 오케스트레이션 계층",
                "inst": "inst-cp1",
                "summary": "Control Plane cp1(172.20.0.86, FIP 192.168.120.226, VIP 10.10.1.100), Worker w1(172.20.0.180, Calico)",
                "areas": [("k3s 서버 및 클러스터 설정", "k3s", "https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s"),
                          ("Pod 배포 및 Service(NodePort 30080)", "app", "https://figteam.ktci5.kr/#cfg/inst/inst-cp1/app"),
                          ("ArgoCD GitOps 배포 관리", "argocd", "https://figteam.ktci5.kr/#cfg/inst/inst-cp1/argocd"),
                          ("Worker w1 에이전트 설정", "agent", "https://figteam.ktci5.kr/#cfg/inst/inst-w1/agent")]
            },
            {
                "title": "KT Cloud Edge 인입 WAF 및 WireGuard 허브 계층",
                "inst": "inst-ktedge",
                "summary": "KT Edge(14.63.212.190), Nginx WAF 10s 마이크로캐싱, 3사 WireGuard 허브(10.200.0.1:51820)",
                "areas": [("Nginx WAF 및 프록시 설정", "nginx", "https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/nginx"),
                          ("WireGuard 허브 wg0", "wg", "https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/wg"),
                          ("KT 워커 조인 설계 (하이브리드)", "join", "https://figteam.ktci5.kr/#cfg/inst/inst-ktw1/join")]
            },
            {
                "title": "AWS DR Pilot-Light 및 복구 오케스트레이터 계층",
                "inst": "inst-awsdr",
                "summary": "aws-dr(10.51.1.165, MySQL Replica), aws-ctl(10.50.1.85:8080, Orchestrator API)",
                "areas": [("DR DB Replica 설정 (ch_dr)", "mysql", "https://figteam.ktci5.kr/#cfg/inst/inst-awsdr/mysql"),
                          ("복구 오케스트레이터 REST API", "api", "https://figteam.ktci5.kr/#cfg/inst/inst-awsctl/api")]
            }
        ]

        for s in subsystems:
            lines.append(f"### 📍 {s['title']}")
            lines.append(f"- **실측 개요**: {s['summary']}")
            lines.append("- **사용자가 직접 접속하여 설정 및 입력할 공식 웹 URL:**")
            for aname, aid, aurl in s["areas"]:
                lines.append(f"  • **{aname}**: 👉 [{aurl}]({aurl})")
            lines.append("")

        lines.append("---\n")
        lines.append("## 2. 클러스터 전체 공통 변수 실측값\n")
        vars_res = self.core.get_common_variables()
        for v in vars_res:
            if "S1_" not in v["variable"]:
                lines.append(f"- **`{v['variable']}`**: `{v['value']}` — {v['usage']}")
        lines.append("\n---\n")
        lines.append("> 🔒 **운영 원칙 안내**: 본 마크다운은 s1을 제외한 클러스터 전반의 실측 지식 소스입니다. 실제 모든 설정 변경, 파라미터 입력, 명령어 실행은 위 명시된 공식 웹 콘솔 URL에서 직접 진행하십시오.\n")
        return "\n".join(lines)

    def build_instance_markdown(self, inst_id: str) -> str:
        """특정 인스턴스 또는 s1 제외 전체 클러스터의 상세 현황 구조 및 해당 웹 설정 페이지 직결 마크다운"""
        key = inst_id.strip().lower()
        if key in ("cluster", "services", "all", "cloud"):
            return self.build_cluster_unified_markdown()

        if not key.startswith("inst-") and f"inst-{key}" in self.core.pages:
            key = f"inst-{key}"
        elif key in ("db", "db01"):
            key = "inst-db01"
        elif key == "ktedge":
            key = "inst-ktedge"
        elif key == "awsdr":
            key = "inst-awsdr"
        elif key == "awsctl":
            key = "inst-awsctl"

        if key not in self.core.pages:
            return f"# 오류: 인스턴스 '{inst_id}'를 찾을 수 없습니다.\n\n사용 가능한 대상: `s1` (호스트), `cluster` (s1 제외 전체 클러스터 통합), `db01`, `controller`, `cp1`, `w1`, `ktedge`, `awsdr`\n"

        p = self.core.pages[key]
        lines = []
        lines.append(f"# [{p.get('title')}] 웹 현황 구조 및 직접 설정 명세서\n")
        lines.append(f"> **클라우드 / 태그**: `{p.get('cloud')}` / `{p.get('tag')}`")
        lines.append(f"> **상태 / 단계**: `{p.get('status')}` / `{p.get('steps')}`")
        lines.append(f"> **개요**: {p.get('desc')}\n")

        if p.get("specs"):
            lines.append("### ⚙️ 실측 하드웨어 / 네트워크 사양")
            for s in p.get("specs"):
                if isinstance(s, (list, tuple)) and len(s) >= 2:
                    lines.append(f"- **{s[0]}**: `{s[1]}`")
                elif isinstance(s, dict):
                    lines.append(f"- **{s.get('label')}**: `{s.get('val')}`")
            lines.append("")

        lines.append("---\n")
        lines.append("### 🌐 사용자가 직접 접속하여 설정 및 입력할 웹 화면 링크 (Areas)\n")

        for a in p.get("areas", []):
            aid = a.get("id")
            aname = a.get("name")
            web_url = f"https://figteam.ktci5.kr/#cfg/inst/{key}/{aid}"
            lines.append(f"#### 📍 {aname} (`{aid}`)")
            lines.append(f"👉 **공식 웹 설정 화면 URL**: [{web_url}]({web_url})\n")

            if a.get("design"):
                lines.append("**설계 원칙 및 배경:**")
                for d in a.get("design"):
                    lines.append(f"- {d}")
                lines.append("")

            if a.get("config"):
                lines.append("**설정 파일 및 코드 블록:**")
                for c in a.get("config"):
                    lines.append(f"```ini\n# [{c.get('label')}] (경로: {c.get('path', '설정 파일')})\n{c.get('code', '').strip()}\n```\n")

            if a.get("commands"):
                lines.append("**운영 및 점검 명령어 (웹 콘솔 안전가드 터미널에서 실행 권장):**")
                for cmd in a.get("commands"):
                    if isinstance(cmd, dict):
                        lines.append(f"```bash\n# [{cmd.get('label', '')}] ({cmd.get('cat', '')})\n{cmd.get('code', '').strip()}\n```\n")
                    elif isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                        lines.append(f"- `{cmd[0]}` ({cmd[1]})\n")
                lines.append("")

            if a.get("trouble"):
                lines.append("**트러블슈팅 및 장애 복구:**")
                for tr in a.get("trouble"):
                    if isinstance(tr, (list, tuple)):
                        symptom = tr[0] if len(tr) > 0 else ""
                        cause = tr[1] if len(tr) > 1 else ""
                        chk = tr[2] if len(tr) > 2 else ""
                        fix = tr[3] if len(tr) > 3 else ""
                        lines.append(f"- **증상**: {symptom} ➔ **원인**: {cause}")
                        if chk:
                            lines.append(f"  - 점검: `{chk}`")
                        if fix:
                            lines.append(f"  - 해결: `{fix}`")
                    elif isinstance(tr, dict):
                        lines.append(f"- **증상**: {tr.get('symptom')} ➔ **원인**: {tr.get('cause')}")
                        if tr.get("fix"):
                            lines.append(f"  - 해결: `{tr.get('fix')}`")
                lines.append("")

            lines.append("---\n")

        lines.append("> 🔒 **운영 원칙 안내**: AI는 본 명세를 읽고 기술적 조언 및 분석을 제공합니다. 실제 설정 입력, 파일 저장, 안전 가드가 포함된 명령어 실행은 위 명시된 공식 웹 콘솔 URL에서 직접 진행하십시오.\n")
        return "\n".join(lines)

    def handle_md_models(self):
        """OpenAI 호환 모델 목록 반환 (/md/v1/models)"""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        now_ts = int(time.time())
        models_data = {
            "object": "list",
            "data": [
                {"id": "figteam-fact-grounded", "object": "model", "created": now_ts, "owned_by": "figteam"},
                {"id": "gpt-4o", "object": "model", "created": now_ts, "owned_by": "figteam"},
                {"id": "gpt-4o-mini", "object": "model", "created": now_ts, "owned_by": "figteam"},
                {"id": "gemini-2.5-flash", "object": "model", "created": now_ts, "owned_by": "figteam"},
                {"id": "claude-3-5-sonnet", "object": "model", "created": now_ts, "owned_by": "figteam"}
            ]
        }
        self.wfile.write(json.dumps(models_data, ensure_ascii=False).encode("utf-8"))

    def build_grounding_context(self) -> str:
        """AI 프록시 및 로컬 훅 주입용 최신 실측 마크다운 컨텍스트"""
        vars_res = self.core.get_common_variables()
        vars_lines = [f"- **{v['variable']}**: `{v['value']}` ({v['usage']})" for v in vars_res]
        vars_text = "\n".join(vars_lines)

        topo = self.core.get_topology()
        matrix = self.core.get_auth_matrix()

        return f"""# FIGTEAM 3사 하이브리드 멀티클라우드 실측 인프라 사실 지침 (Ground Truth)

> **실측 기준 일자**: {self.core.measured} (온프렘 OpenStack RAM 증설 및 3사 실측 최신화 완료)
> **공식 웹 포털 (설정 및 안전가드 터미널)**: https://figteam.ktci5.kr/#cfg/

---

## 🔒 절대 보안 및 웹 설정 유도 원칙 (MUST FOLLOW)
1. **읽기 전용 기술 조언 전담**: 당신은 '읽기 전용(Read-Only)' 실측 기반 기술 조언 및 원인 분석 어드바이저입니다. 절대로 직접 명령어를 원격 실행하거나 설정을 대리 변경할 수 없습니다.
2. **웹 콘솔 직접 실행 유도**: 모든 실제 인프라 설정 변경, 서비스 재시작, DB 복구, 파괴적 조치 명령어 실행은 팀원이 직접 웹 포털(https://figteam.ktci5.kr/#cfg)에 접속하여 안전 가드가 적용된 터미널 러너(`▶ 실행`)로 수행하도록 명확한 웹 화면 링크를 제공하여 유도하십시오.
3. **분야별 공식 웹 설정 페이지 링크**:
   - **DB 클러스터 (Primary/Replica/GTID)**: https://figteam.ktci5.kr/#cfg/inst/inst-db01/data
   - **온프렘 호스트 & 점프호스트(s1)**: https://figteam.ktci5.kr/#cfg/inst/inst-s1/access
   - **OpenStack Controller (RAM 14GB 증설)**: https://figteam.ktci5.kr/#cfg/inst/inst-controller/core
   - **OpenStack Compute 1·3·4 (RAM 8GB 증설)**: https://figteam.ktci5.kr/#cfg/inst/inst-compute1/compute
   - **K8s 클러스터 (cp1 / w1)**: https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s
   - **KT Cloud Edge (Nginx WAF 10s 캐싱)**: https://figteam.ktci5.kr/#cfg/inst/inst-ktedge/proxy
   - **AWS DR Pilot-Light (aws-dr, aws-ctl)**: https://figteam.ktci5.kr/#cfg/inst/inst-awsdr/replica
   - **3사 전체 엔드투엔드 토폴로지**: https://figteam.ktci5.kr/#cfg/overview

---

## 1. 3사 하이브리드 아키텍처 및 트래픽 경로
{topo.get('architecture', '')}

---

## 2. 19대 핵심 공통 변수 실측값
{vars_text}

---

## 3. 계층별 접속 인증 매트릭스
{matrix.get('auth_matrix_text', '')}
"""

    def generate_fact_fallback_response(self, user_query: str) -> str:
        """키워드 기반 실시간 사실 분석 및 공식 웹 콘솔 유도 응답 생성"""
        q_lower = user_query.lower()

        if any(k in q_lower for k in ["db", "mysql", "gtid", "복제", "데이터", "3306"]):
            return (
                "### 🔍 FIGTEAM DB 클러스터 실측 사양 및 점검 분석\n\n"
                "* **Primary DB (온프렘 OpenStack)**: `10.10.2.10:3306` (`inst-db01`, MySQL 8.4 LTS, GTID ON, `enforce_gtid_consistency=ON`)\n"
                "* **Replica DB (AWS DR Pilot-Light)**: `10.51.1.165:3306` (`aws-dr`, 채널 `ch_dr`, GTID 자동 위치 지정)\n"
                "* **연결 메시망**: KT Edge 허브(`10.200.0.1:51820`)를 통한 WireGuard wg0 터널 암호화 복제\n\n"
                "**주요 장애 점검 포인트**:\n"
                "1. 복제 상태 확인: `SHOW REPLICA STATUS FOR CHANNEL 'ch_dr'\\G` (Replica_IO_Running, Replica_SQL_Running 확인)\n"
                "2. GTID 지연 여부: `SELECT @@GLOBAL.gtid_executed;` 와 Master의 실행 트랜잭션 비교\n"
                "3. WireGuard 메시망 상태: `ssh s1 sudo wg show wg-kt` 또는 KT Edge ping 점검\n\n"
                "👉 **실제 복구 및 설정 작업은 웹 콘솔에서 직접 수행하십시오**:\n"
                "보안 가이드라인에 따라 모든 DB 설정 조회 및 안전 가드가 적용된 복구 명령어 실행은 공식 웹 포털에서 진행하셔야 합니다.\n"
                "🔗 **웹 콘솔 바로가기**: [https://figteam.ktci5.kr/#cfg/inst/inst-db01/data](https://figteam.ktci5.kr/#cfg/inst/inst-db01/data)\n\n"
                "> 🔒 **보안 안내**: 본 AI는 실측 기반 질의응답(Read-Only) 전용입니다. 실제 변경 및 안전 가드 명령어 실행은 위 웹 콘솔을 이용해 주십시오."
            )

        if any(k in q_lower for k in ["ram", "메모리", "컨트롤러", "스왑", "swap", "증설", "고갈", "oom"]):
            return (
                "### 🔍 FIGTEAM OpenStack 클러스터 메모리 실측 현황 (2026-11-27 기준)\n\n"
                "* **물리 호스트 s1 (`10.10.10.8`)**: 20 vCPU / 30GB RAM, 고속 NVMe 스왑(`swap.img` 8GB) 활성화 완료\n"
                "* **Controller 노드 (`192.168.120.160`)**: 기존 10GB(99% 고갈)에서 **14GB RAM**으로 증설 완료 + 내부 스왑 4GB 신규 확보 (현재 가용 메모리 8.3GB, 38% 안정권)\n"
                "* **Compute 노드 (`161, 163, 164`)**: 전 노드 **8GB RAM**으로 균등 증설 완료 (노드 162 compute2는 미사용 삭제)\n\n"
                "**운영 권고**:\n"
                "Controller 노드는 Keystone, Nova, Glance, Neutron, RabbitMQ, MariaDB 제어 전용이므로 사용자 VM 인스턴스는 반드시 8GB 컴퓨트 노드군으로 스케줄링하십시오.\n\n"
                "👉 **상세 설정 및 노드 제어는 공식 웹 콘솔에서 직접 수행하십시오**:\n"
                "🔗 **Controller 설정 화면**: [https://figteam.ktci5.kr/#cfg/inst/inst-controller/core](https://figteam.ktci5.kr/#cfg/inst/inst-controller/core)\n"
                "🔗 **Compute 노드 화면**: [https://figteam.ktci5.kr/#cfg/inst/inst-compute1/compute](https://figteam.ktci5.kr/#cfg/inst/inst-compute1/compute)\n\n"
                "> 🔒 **보안 안내**: 본 AI는 읽기 전용 실측 어드바이저입니다. 실제 설정 변경은 웹 콘솔에서 안전 가드를 통해 진행하십시오."
            )

        if any(k in q_lower for k in ["ssh", "접속", "키", "인증", "바스천", "s1", "터미널"]):
            return (
                "### 🔍 FIGTEAM 인프라 접속 및 키 매트릭스 안내\n\n"
                "* **단일 점프호스트(Bastion)**: 물리 호스트 `s1 (10.10.10.8, t1-vm2)`\n"
                "* **팀원 진입 키**: 개인키 `~/.ssh/id_ed25519` 사용 (`ssh s1`)\n"
                "* **내부 VM 접속 경로**: s1 호스트의 `~/bin/osx <노드> <명령>` 래퍼 스크립트 또는 `~/.ssh/config`의 `ProxyJump s1` 규칙 활용\n\n"
                "👉 **전체 인프라 계층(물리, OpenStack, K8s, DB, AWS, WireGuard) 접속 키 매트릭스 전문**:\n"
                "🔗 **웹 콘솔 바로가기**: [https://figteam.ktci5.kr/#cfg/inst/inst-s1/access](https://figteam.ktci5.kr/#cfg/inst/inst-s1/access)\n\n"
                "> 🔒 **보안 안내**: 본 AI는 읽기 전용 안내를 제공합니다. 명령어 실행은 웹 콘솔 내 플로팅 터미널 러너를 이용하십시오."
            )

        if any(k in q_lower for k in ["k8s", "쿠버", "cp1", "w1", "파드", "6443", "vip"]):
            return (
                "### 🔍 FIGTEAM Kubernetes (k8s) PaaS 실측 사양\n\n"
                "* **Control Plane (cp1)**: `172.20.0.86` (FIP: `192.168.120.226`, VIP: `10.10.1.100:80`)\n"
                "* **Worker Node (w1)**: `172.20.0.180` (Calico CNI, Pod CIDR `10.244.0.0/16`)\n"
                "* **외부 노출 포트**: NodePort `30080` (VIP 10.10.1.100:80 ➔ DNAT 192.168.120.226:30080)\n\n"
                "👉 **K8s 클러스터 설정 및 매니페스트 확인**:\n"
                "🔗 **웹 콘솔 바로가기**: [https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s](https://figteam.ktci5.kr/#cfg/inst/inst-cp1/k8s)\n\n"
                "> 🔒 **보안 안내**: 실제 kubectl 명령어 실행 및 배포는 웹 콘솔에서 안전 가드를 거쳐 직접 진행해 주십시오."
            )

        # 기본 일반 응답
        return (
            "### 🔍 FIGTEAM 하이브리드 인프라 실측 브리핑\n\n"
            f"* **실측 기준 일자**: {self.core.measured}\n"
            "* **사용자 진입**: `https://minwon.ktci5.kr` (Cloudflare) ➔ KT Edge (`14.63.212.190`, Nginx WAF 10s 캐싱)\n"
            "* **3사 메시 터널**: WireGuard wg0 (`10.200.0.1` KT Hub) ↔ wg-kt (`10.200.0.2` 온프렘 s1)\n"
            "* **온프렘 호스트**: s1 (`10.10.10.8`, 20 vCPU / 30GB RAM, NVMe 8GB Swap)\n"
            "* **OpenStack 노드**: Controller (`192.168.120.160`, RAM 14GB 증설), Compute 1·3·4 (각 8GB)\n"
            "* **데이터 계층**: DB-01 (`10.10.2.10`, MySQL 8.4 Primary) ↔ AWS-DR (`10.51.1.165`, Replica Pilot-Light)\n\n"
            "👉 **질의하신 인프라의 모든 설계, 설정 코드, 운영 명령어 및 트러블슈팅은 공식 웹 포털에 집대성되어 있습니다**:\n"
            "🔗 **FIGTEAM 공식 웹 콘솔**: [https://figteam.ktci5.kr/#cfg/overview](https://figteam.ktci5.kr/#cfg/overview)\n\n"
            "> 🔒 **보안 안내**: 본 AI는 실측 기반 질의응답(Read-Only) 전용 어드바이저입니다. 실제 설정 변경 및 명령어 실행은 안전 가드가 포함된 공식 웹 콘솔에서 직접 수행하셔야 합니다."
        )

    def handle_md_chat_completions(self, body_json: dict[str, Any]):
        """OpenAI 표준 호환 Chat Completion 프록시/게이트웨이 핸들러"""
        stream = body_json.get("stream", False)
        model = body_json.get("model", "figteam-fact-grounded")
        messages = body_json.get("messages", [])

        # 마지막 사용자 질의 추출
        last_user_query = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user_query = m.get("content", "")
                break

        auth_header = self.headers.get("Authorization", "")
        api_key = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""

        # 외부 LLM 포워딩 시도 (API 키가 주어졌을 때)
        upstream_resp_text = None
        if api_key and api_key not in ("figteam", "dummy", "test"):
            try:
                grounding_sys = {
                    "role": "system",
                    "content": self.build_grounding_context()
                }
                forward_messages = [grounding_sys]
                for msg in messages:
                    if msg.get("role") != "system":
                        forward_messages.append(msg)

                # OpenAI 엔드포인트 기본값
                target_url = "https://api.openai.com/v1/chat/completions"
                if api_key.startswith("AIza"):
                    target_url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                elif api_key.startswith("gsk_"):
                    target_url = "https://api.groq.com/openai/v1/chat/completions"

                fwd_payload = {
                    "model": model if model != "figteam-fact-grounded" else "gpt-4o-mini",
                    "messages": forward_messages,
                    "stream": False,
                    "temperature": 0.2
                }

                req = urllib.request.Request(
                    target_url,
                    data=json.dumps(fwd_payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}"
                    },
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as u_resp:
                    if u_resp.status == 200:
                        u_data = json.loads(u_resp.read().decode("utf-8"))
                        choices = u_data.get("choices", [])
                        if choices:
                            upstream_resp_text = choices[0].get("message", {}).get("content", "")
            except Exception:
                pass  # 실패 시 내장 사실 엔진으로 폴백

        # 최종 답변 텍스트 결정
        final_answer = upstream_resp_text or self.generate_fact_fallback_response(last_user_query)

        chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        now_ts = int(time.time())

        # 스트리밍 응답 (SSE)
        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            # 첫 chunk (role)
            chunk_role = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": now_ts,
                "model": model,
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]
            }
            self.wfile.write(f"data: {json.dumps(chunk_role, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

            # 본문 내용 스트리밍 (글자 블록 단위 전송)
            step_size = 40
            for i in range(0, len(final_answer), step_size):
                piece = final_answer[i:i + step_size]
                chunk_piece = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": now_ts,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]
                }
                self.wfile.write(f"data: {json.dumps(chunk_piece, ensure_ascii=False)}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.01)

            # 마지막 chunk (DONE)
            chunk_end = {
                "id": chat_id,
                "object": "chat.completion.chunk",
                "created": now_ts,
                "model": model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            }
            self.wfile.write(f"data: {json.dumps(chunk_end, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            return

        # 일반 단발 JSON 응답
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        resp_data = {
            "id": chat_id,
            "object": "chat.completion",
            "created": now_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": final_answer
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": max(1, len(last_user_query)),
                "completion_tokens": max(1, len(final_answer)),
                "total_tokens": max(1, len(last_user_query) + len(final_answer))
            }
        }
        self.wfile.write(json.dumps(resp_data, ensure_ascii=False, indent=2).encode("utf-8"))

    def handle_rest_api(self, subpath: str, qs: dict[str, list[str]]):
        """ChatGPT Actions 및 일반 REST 클라이언트를 위한 직결 REST API 핸들러"""
        try:
            res_data: Any = None
            if subpath == "topology":
                res_data = self.core.get_topology()
            elif subpath == "variables":
                q = qs.get("query", [""])[0] or qs.get("q", [""])[0]
                res_data = self.core.get_common_variables(q)
            elif subpath == "instance":
                inst_id = qs.get("instance_id", [""])[0] or qs.get("id", [""])[0]
                res_data = self.core.get_instance_details(inst_id)
            elif subpath == "area":
                inst_id = qs.get("instance_id", [""])[0] or qs.get("instance", [""])[0]
                area_id = qs.get("area_id", [""])[0] or qs.get("area", [""])[0]
                res_data = self.core.get_area_config(inst_id, area_id)
            elif subpath in ("auth-matrix", "auth_matrix"):
                res_data = self.core.get_auth_matrix()
            elif subpath == "troubleshoot":
                q = qs.get("query", [""])[0] or qs.get("q", [""])[0]
                res_data = self.core.search_troubleshooting(q)
            elif subpath == "steps":
                no = qs.get("step_no", [""])[0] or qs.get("no", [""])[0]
                res_data = self.core.get_steps_guide(no)
            elif subpath == "raw":
                sec = qs.get("section", [""])[0]
                res_data = self.core.query_config_raw(sec)
            else:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"알 수 없는 REST API 엔드포인트: {subpath}"}, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res_data, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"REST API 처리 실패: {e}"}, ensure_ascii=False).encode("utf-8"))

    def get_openapi_spec(self) -> dict[str, Any]:
        """ChatGPT Custom Actions / GPTs 표준 OpenAPI 3.1.0 스키마 반환"""
        return {
            "openapi": "3.1.0",
            "info": {
                "title": "FIGTEAM Hybrid Multi-Cloud #cfg Knowledge API",
                "version": "1.0.0",
                "description": "온프레미스(s1/OpenStack), KT Cloud, AWS DR 3사 하이브리드 인프라 실측 사양, 공통 변수, 인증 매트릭스, 트러블슈팅 가이드를 질의하는 API"
            },
            "servers": [
                {"url": "https://figteam.ktci5.kr/mcp/api"}
            ],
            "paths": {
                "/topology": {
                    "get": {
                        "operationId": "getTopology",
                        "summary": "전체 인프라 엔드투엔드 토폴로지 및 네트워크 경로 조회",
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                },
                "/variables": {
                    "get": {
                        "operationId": "getCommonVariables",
                        "summary": "19대 핵심 공통 변수 실측값 검색",
                        "parameters": [
                            {"name": "query", "in": "query", "required": False, "schema": {"type": "string"}, "description": "변수명 또는 용도 검색어 (예: S1_HOST, OS_CONTROLLER, RAM)"}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "array"}}}}}
                    }
                },
                "/instance": {
                    "get": {
                        "operationId": "getInstanceDetails",
                        "summary": "특정 인스턴스 사양 및 관리 영역 목록 조회",
                        "parameters": [
                            {"name": "instance_id", "in": "query", "required": True, "schema": {"type": "string"}, "description": "인스턴스명 (s1, controller, cp1, w1, db01, ktedge, awsdr, awsctl)"}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                },
                "/area": {
                    "get": {
                        "operationId": "getAreaConfig",
                        "summary": "인스턴스별 세부 영역 설계, 설정 코드, 운영 명령어, 트러블슈팅 조회",
                        "parameters": [
                            {"name": "instance_id", "in": "query", "required": True, "schema": {"type": "string"}},
                            {"name": "area_id", "in": "query", "required": True, "schema": {"type": "string"}}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                },
                "/auth-matrix": {
                    "get": {
                        "operationId": "getAuthMatrix",
                        "summary": "전체 인프라 계층 접속 계정, 키 파일 경로, 권한 종합 매트릭스 조회",
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                },
                "/troubleshoot": {
                    "get": {
                        "operationId": "searchTroubleshooting",
                        "summary": "장애 증상 및 오류 키워드로 해결 조치법 검색",
                        "parameters": [
                            {"name": "query", "in": "query", "required": True, "schema": {"type": "string"}, "description": "오류 키워드 (예: 6443, Permission denied, DNS, 메모리, MTU)"}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "array"}}}}}
                    }
                },
                "/steps": {
                    "get": {
                        "operationId": "getStepsGuide",
                        "summary": "S0~S12 인프라 구축 및 장애 복구 선행 순서와 검증 Gate 조회",
                        "parameters": [
                            {"name": "step_no", "in": "query", "required": False, "schema": {"type": "string"}, "description": "단계 번호 (예: S0, S1)"}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                },
                "/raw": {
                    "get": {
                        "operationId": "queryConfigRaw",
                        "summary": "#cfg 사이트 구조화 원본 데이터 섹션별 질의",
                        "parameters": [
                            {"name": "section", "in": "query", "required": False, "schema": {"type": "string"}, "description": "섹션명 (variables, steps, instances, domains, scripts)"}
                        ],
                        "responses": {"200": {"description": "성공", "content": {"application/json": {"schema": {"type": "object"}}}}}
                    }
                }
            }
        }

    def get_installer_script(self) -> str:
        """클로드/GPT/AGY/커서/제미니 원클릭 만능 연동 스크립트"""
        return r'''#!/usr/bin/env bash
# ==============================================================================
# FIGTEAM #cfg MCP Server One-Click Universal Setup
# Supports: Claude Desktop · Claude Code · Cursor · Windsurf · AGY · Gemini · Codex
# Endpoint: https://figteam.ktci5.kr/mcp/sse
# ==============================================================================
set -e

SSE_URL="https://figteam.ktci5.kr/mcp/sse"
SERVER_NAME="figteam-cfg"

echo "======================================================================"
echo "  🚀 FIGTEAM #cfg MCP Server 만능 연동 도구 (Universal Setup)"
echo "  연동 대상: Claude Desktop · Claude Code · Cursor · AGY · Gemini · Codex"
echo "  엔드포인트: ${SSE_URL}"
echo "======================================================================"

DETECTED=0

# Python JSON helper
update_json_mcp() {
  local cfg_file="$1"
  python3 -c "
import json, os, sys

path = os.path.expanduser('$cfg_file')
os.makedirs(os.path.dirname(path), exist_ok=True)
data = {}
if os.path.exists(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        data = {}

if 'mcpServers' not in data:
    data['mcpServers'] = {}

data['mcpServers']['$SERVER_NAME'] = {'url': '$SSE_URL'}

with open(path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f'   ✅ 설정 파일 반영 완료: {path}')
"
}

# 1. Claude Desktop
CLAUDE_CONFIG=""
if [[ "$OSTYPE" == "darwin"* ]]; then
  CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
elif [[ "$OSTYPE" == "linux"* ]]; then
  CLAUDE_CONFIG="$HOME/.config/Claude/claude_desktop_config.json"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
  CLAUDE_CONFIG="$APPDATA/Claude/claude_desktop_config.json"
fi

echo ""
echo "[1/6] Claude Desktop 점검..."
if [[ -n "$CLAUDE_CONFIG" ]]; then
  update_json_mcp "$CLAUDE_CONFIG"
  DETECTED=$((DETECTED + 1))
fi

# 2. Claude Code CLI
echo ""
echo "[2/6] Claude Code (CLI) 점검..."
if command -v claude >/dev/null 2>&1; then
  echo "   ⚙️  claude mcp add 실행 중..."
  claude mcp add --transport sse "$SERVER_NAME" "$SSE_URL" 2>&1 || true
  echo "   ✅ Claude Code 연동 완료"
  DETECTED=$((DETECTED + 1))
else
  echo "   ℹ️  Claude Code CLI 미설치 (건너뜀)"
fi

# 3. Cursor & Windsurf
echo ""
echo "[3/6] Cursor / Windsurf 전역 설정 점검..."
CURSOR_GLOBAL="$HOME/.cursor/mcp.json"
update_json_mcp "$CURSOR_GLOBAL"
DETECTED=$((DETECTED + 1))

# 4. Google Antigravity (AGY)
echo ""
echo "[4/6] Google Antigravity (AGY) 점검..."
if command -v agy >/dev/null 2>&1; then
  echo "   ⚙️  agy mcp add 실행 중..."
  agy mcp add "$SERVER_NAME" "$SSE_URL" 2>&1 || true
  echo "   ✅ AGY 연동 완료"
  DETECTED=$((DETECTED + 1))
else
  echo "   ℹ️  agy CLI 미설치 (건너뜀)"
fi

# 5. Gemini CLI & Config
echo ""
echo "[5/6] Gemini CLI & Settings 점검..."
GEMINI_SETTINGS="$HOME/.gemini/settings.json"
if [[ -f "$GEMINI_SETTINGS" || -d "$HOME/.gemini" ]]; then
  update_json_mcp "$GEMINI_SETTINGS"
  DETECTED=$((DETECTED + 1))
fi
if command -v gemini >/dev/null 2>&1; then
  echo "   ⚙️  gemini mcp add 실행 중..."
  gemini mcp add "$SERVER_NAME" "$SSE_URL" 2>&1 || true
  echo "   ✅ Gemini CLI 연동 완료"
  DETECTED=$((DETECTED + 1))
fi

# 6. Codex / OpenAI CLI
echo ""
echo "[6/6] Codex 설정 점검..."
CODEX_CONFIG="$HOME/.codex/config.json"
if [[ -d "$HOME/.codex" || -f "$CODEX_CONFIG" ]]; then
  update_json_mcp "$CODEX_CONFIG"
  DETECTED=$((DETECTED + 1))
fi

echo ""
echo "======================================================================"
echo "  🎉 FIGTEAM #cfg MCP 서버 연동이 성공적으로 완료되었습니다!"
echo "  총 ${DETECTED}개 클라이언트/설정 파일이 등록되었습니다."
echo ""
echo "  • SSE 엔드포인트: ${SSE_URL}"
echo "  • ChatGPT Custom Actions 스펙: https://figteam.ktci5.kr/mcp/openapi.json"
echo "  • Direct RPC: https://figteam.ktci5.kr/mcp/rpc"
echo "======================================================================"
'''

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
