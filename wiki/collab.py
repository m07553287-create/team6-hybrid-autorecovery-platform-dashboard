"""팀 AI 협업 공유 피드 · OAuth 2.0 웹 로그인 커넥터 · Discord Webhook 중계."""
from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from wiki import auth, docs
from wiki.errors import ApiError
from wiki.guard import find_secret

SHARE_LIMIT = 200
OAUTH_CODE_TTL = 300
OAUTH_TOKEN_TTL = 30 * 24 * 3600

STATUS_META: dict[str, tuple[str, int]] = {
    "in_progress": ("진행중", 0x3B82F6),
    "done": ("완료", 0x10B981),
    "check_needed": ("확인필요", 0xF59E0B),
    "incident": ("장애/이슈", 0xEF4444),
    "info": ("공유", 0x64748B),
}

WEBHOOK_RE = re.compile(r"https?://(?:canary\.|ptb\.)?discord(?:app)?\.com/api/webhooks/\S+", re.I)

DEFAULT_REDIRECT_PREFIXES = (
    "https://chat.openai.com/aip/",
    "https://chatgpt.com/aip/",
    "https://figteam.ktci5.kr/",
)

_CROSSCHECK_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(fip|nodeport|30080|upstream|nginx|kt-edge|ktedge)", re.I),
        "KT Edge upstream.conf 및 s1 VIP DNAT(10.10.1.100→192.168.120.226:30080) 영향 확인 필요",
    ),
    (
        re.compile(r"(mysql|db01|db-01|gtid|3306|repl|binlog)", re.I),
        "AWS DR(10.51.1.165) MySQL GTID 복제 채널(ch_dr) 정합성 확인 필요",
    ),
    (
        re.compile(r"(wireguard|wg0|10\.200|endpoint|mtu)", re.I),
        "KT Edge wg0 허브(10.200.0.1) 및 3사 peer AllowedIPs/MTU 확인 필요",
    ),
    (
        re.compile(r"(k3s|cp1|w1|calico|flannel|6443|argocd)", re.I),
        "k3s cp1/w1 노드 상태 및 6443/CNI 통신 영향 확인 필요",
    ),
    (
        re.compile(r"(controller|compute|openstack|nova|neutron|sg-)", re.I),
        "OpenStack 보안그룹·라우터(rt-edge/rt-data) 및 하이퍼바이저 메모리 확인 필요",
    ),
]


def _sha256(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def _check_no_secret(text: str, field: str) -> None:
    if not text:
        return
    if WEBHOOK_RE.search(text):
        raise ApiError(422, "Discord Webhook URL은 공유 내용에 포함할 수 없습니다.", {"field": field})
    hit = find_secret(text, field)
    if hit:
        raise ApiError(422, "비밀값처럼 보이는 내용은 저장할 수 없습니다. <자리표시> 형태로 바꾸세요.", hit)


def _clean_text(val: Any, field: str, max_len: int, required: bool = False, default: str = "") -> str:
    if val in (None, ""):
        if required:
            raise ApiError(422, f"{field} 내용을 입력하세요", {"field": field})
        return default
    if not isinstance(val, str):
        raise ApiError(422, f"{field} 형식이 올바르지 않습니다", {"field": field})
    text = val.strip()
    if required and not text:
        raise ApiError(422, f"{field} 내용을 입력하세요", {"field": field})
    if len(text) > max_len:
        raise ApiError(422, f"{field} 길이는 {max_len}자 이하여야 합니다", {"field": field})
    _check_no_secret(text, field)
    return text


def _normalize_cfg_url(val: Any) -> str:
    if val in (None, ""):
        return ""
    if not isinstance(val, str):
        raise ApiError(422, "cfg_url 형식이 올바르지 않습니다", {"field": "cfg_url"})
    raw = val.strip()
    if not raw:
        return ""
    if len(raw) > 300:
        raise ApiError(422, "cfg_url 은 300자 이하여야 합니다", {"field": "cfg_url"})
    if raw.startswith("#cfg"):
        raw = "https://figteam.ktci5.kr/" + raw
    if not raw.startswith("https://figteam.ktci5.kr/"):
        raise ApiError(422, "cfg_url 은 https://figteam.ktci5.kr/ 또는 #cfg 로 시작해야 합니다", {"field": "cfg_url"})
    return raw


def build_crosscheck_hints(area: str, summary: str) -> list[str]:
    text = f"{area or ''} {summary or ''}"
    hints: list[str] = []
    for pat, hint in _CROSSCHECK_RULES:
        if pat.search(text):
            hints.append(hint)
    return hints


def is_allowed_redirect(uri: str) -> bool:
    if not isinstance(uri, str):
        return False
    u = uri.strip()
    if not u or any(ch in u for ch in ("\r", "\n", "\t", " ")):
        return False
    parsed = urllib.parse.urlparse(u)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        return False
    extra = [x.strip() for x in os.environ.get("FIGTEAM_OAUTH_REDIRECT_ALLOWLIST", "").split(",") if x.strip()]
    prefixes = DEFAULT_REDIRECT_PREFIXES + tuple(extra)
    if any(u.startswith(p) for p in prefixes):
        return True
    if parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"):
        return True
    return False


def oauth_client_config() -> tuple[str, str]:
    cid = os.environ.get("FIGTEAM_OAUTH_CLIENT_ID", "figteam-ai-connector").strip() or "figteam-ai-connector"
    csec = os.environ.get("FIGTEAM_OAUTH_CLIENT_SECRET", "").strip()
    return cid, csec


def issue_oauth_code(r, s: auth.Session, client_id: str, redirect_uri: str) -> str:
    expected_cid, _ = oauth_client_config()
    if client_id != expected_cid:
        raise ApiError(400, "허용되지 않은 OAuth client_id 입니다", {"field": "client_id"})
    if not is_allowed_redirect(redirect_uri):
        raise ApiError(400, "허용되지 않은 redirect_uri 입니다", {"field": "redirect_uri"})
    code = secrets.token_urlsafe(32)
    payload = {
        "team_id": s.team_id,
        "member": s.member,
        "access_key": s.access_key,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "created_at": int(time.time()),
    }
    r.set(f"fw:oauth:code:{_sha256(code)}", json.dumps(payload, ensure_ascii=False), ex=OAUTH_CODE_TTL)
    return code


def exchange_oauth_code(r, code: str, client_id: str, redirect_uri: str, client_secret: str = "") -> dict[str, Any]:
    expected_cid, expected_sec = oauth_client_config()
    if not client_id or client_id != expected_cid:
        raise ValueError("invalid_client")
    if expected_sec and not hmac.compare_digest(str(client_secret or ""), expected_sec):
        raise ValueError("invalid_client_secret")
    if not code:
        raise ValueError("missing_code")

    ckey = f"fw:oauth:code:{_sha256(code)}"
    raw = r.get(ckey)
    if not raw:
        raise ValueError("expired_or_invalid_code")
    r.delete(ckey)

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ValueError("corrupted_code") from exc

    if data.get("client_id") != client_id or data.get("redirect_uri") != redirect_uri:
        raise ValueError("mismatched_redirect_or_client")

    token = "ft_" + secrets.token_urlsafe(32)
    tk = "fw:oauth:tok:" + _sha256(token)
    team_id = int(data["team_id"])
    p = r.pipeline()
    p.hset(
        tk,
        mapping={
            "team_id": team_id,
            "member": data.get("member") or "게스트",
            "access_key": data.get("access_key") or "",
            "created_at": int(time.time()),
        },
    )
    p.expire(tk, OAUTH_TOKEN_TTL)
    p.sadd(f"fw:oauth:toklist:{team_id}", tk)
    p.execute()

    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": OAUTH_TOKEN_TTL,
        "scope": "read write",
    }


def get_bearer_session(r, auth_header: str) -> auth.Session | None:
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    if not token:
        return None
    tk = "fw:oauth:tok:" + _sha256(token)
    data = r.hgetall(tk)
    if not data:
        return None
    team_id = data.get("team_id")
    slug = r.get(f"fw:teamid:{team_id}") if team_id else None
    t = r.hgetall(f"fw:team:{slug}") if slug else {}
    if not t:
        return None
    return auth.Session(
        team_id=int(team_id),
        slug=slug,
        team_name=t.get("name") or slug,
        member=data.get("member") or "게스트",
        auto=False,
        access_key=data.get("access_key") or "",
    )


def send_discord_webhook(payload: dict[str, Any], webhook_url: str = "") -> dict[str, Any]:
    url = (webhook_url or os.environ.get("FIGTEAM_DISCORD_WEBHOOK_URL", "")).strip()
    if not url:
        return {"sent": False, "reason": "webhook_not_configured"}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "figteam-collab/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"sent": 200 <= resp.status < 300, "status": resp.status}
    except urllib.error.HTTPError as exc:
        return {"sent": False, "reason": f"http_{exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "reason": str(exc)[:160]}


def format_share_embed(entry: dict[str, Any], hints: list[str] | None = None) -> dict[str, Any]:
    status_key = entry.get("status") or "info"
    label, color = STATUS_META.get(status_key, STATUS_META["info"])
    author = entry.get("author") or "게스트"
    ak = entry.get("access_key") or ""
    author_disp = f"{author} ({ak})" if ak else author
    area = entry.get("area") or "general"
    title = entry.get("title") or "진행/설정 공유"

    fields: list[dict[str, Any]] = [
        {"name": "영역/노드", "value": f"`{area}`", "inline": True},
        {"name": "상태", "value": label, "inline": True},
        {"name": "작성자", "value": author_disp, "inline": True},
    ]
    if entry.get("check_request"):
        fields.append({"name": "타 영역 확인 요청", "value": entry["check_request"][:1000], "inline": False})
    if hints:
        fields.append(
            {
                "name": "자동 교차 검증 체크포인트",
                "value": "\n".join(f"• {h}" for h in hints[:5])[:1000],
                "inline": False,
            }
        )
    if entry.get("cfg_url"):
        fields.append({"name": "웹 포털 (#cfg)", "value": entry["cfg_url"], "inline": False})

    embed: dict[str, Any] = {
        "title": f"[{label}] {title}"[:250],
        "description": (entry.get("summary") or "")[:3800],
        "color": color,
        "fields": fields[:10],
        "footer": {"text": f"FIGTEAM 협업 공유 #{entry.get('id', '')} · source={entry.get('source', 'web')}"},
    }
    return {"username": "FIGTEAM 협업 브리지", "embeds": [embed]}


def notify_wiki_change(
    team_slug: str,
    doc_title: str,
    kind: str,
    rev: int,
    member: str,
    access_key: str = "",
    message: str = "",
    action: str = "update",
) -> dict[str, Any]:
    if os.environ.get("FIGTEAM_DISCORD_NOTIFY_WIKI", "1") != "1":
        return {"sent": False, "reason": "wiki_notify_disabled"}
    author_disp = f"{member} ({access_key})" if access_key else member
    act_label = "신규 생성" if action == "create" else "수정"
    payload = {
        "username": "FIGTEAM 위키 알림",
        "embeds": [
            {
                "title": f"[위키 {act_label}] {doc_title or kind} (r{rev})"[:250],
                "description": (message or "구성 문서가 업데이트되었습니다.")[:1000],
                "color": 0x10B981,
                "fields": [
                    {"name": "팀", "value": team_slug, "inline": True},
                    {"name": "문서 종류", "value": kind, "inline": True},
                    {"name": "작성자", "value": author_disp, "inline": True},
                ],
                "footer": {"text": "https://figteam.ktci5.kr/#cfg/"},
            }
        ],
    }
    return send_discord_webhook(payload)


def create_share(
    r,
    s: auth.Session,
    data: dict[str, Any],
    source: str = "web",
    send_discord: bool = True,
) -> dict[str, Any]:
    area = _clean_text(data.get("area"), "area", 60, required=False, default="general")
    status_raw = str(data.get("status") or "info").strip().lower()
    status = status_raw if status_raw in STATUS_META else "info"
    summary = _clean_text(data.get("summary"), "summary", 1500, required=True)
    first_line = summary.splitlines()[0][:60] if summary else "공유"
    title = _clean_text(data.get("title"), "title", 120, required=False, default=first_line)
    check_request = _clean_text(data.get("check_request"), "check_request", 400, required=False, default="")
    cfg_url = _normalize_cfg_url(data.get("cfg_url"))

    share_id = int(r.incr("fw:seq:share"))
    ts = int(time.time())
    hints = build_crosscheck_hints(area, f"{summary} {check_request}")

    entry: dict[str, Any] = {
        "id": share_id,
        "ts": ts,
        "area": area,
        "status": status,
        "status_label": STATUS_META[status][0],
        "title": title,
        "summary": summary,
        "check_request": check_request,
        "cfg_url": cfg_url,
        "author": s.member,
        "access_key": s.access_key,
        "source": source,
        "crosscheck_hints": hints,
        "discord_sent": False,
    }

    discord_res: dict[str, Any] = {"sent": False, "reason": "skipped"}
    if send_discord:
        discord_res = send_discord_webhook(format_share_embed(entry, hints))
        entry["discord_sent"] = bool(discord_res.get("sent"))

    key = f"fw:shares:{s.team_id}"
    p = r.pipeline()
    p.lpush(key, json.dumps(entry, ensure_ascii=False))
    p.ltrim(key, 0, SHARE_LIMIT - 1)
    p.execute()

    if s.access_key:
        auth.record_access(r, s.team_id, s.member, s.access_key, "share", detail=f"{area}: {title[:60]}")

    return {
        "ok": True,
        "share": entry,
        "discord": discord_res,
        "crosscheck_hints": hints,
    }


def list_shares(r, team_id: int, limit: int = 20, area: str = "") -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 20), 100))
    area_q = (area or "").strip().lower()
    out: list[dict[str, Any]] = []
    for raw in r.lrange(f"fw:shares:{team_id}", 0, SHARE_LIMIT - 1):
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if area_q and area_q not in str(item.get("area") or "").lower():
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _fmt_ts(ts: int) -> str:
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(int(ts)))
    except Exception:  # noqa: BLE001
        return "-"


def build_markdown_brief(
    team_slug: str,
    shares: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    include_header: bool = True,
) -> str:
    lines: list[str] = []
    if include_header:
        lines.append(f"## FIGTEAM ({team_slug}) 최신 팀 진행상황 · 설정 공유")
        lines.append("> 인프라 기준표: https://figteam.ktci5.kr/md/v1 | 1클릭 공유: https://figteam.ktci5.kr/api/ai/share-ui\n")

    lines.append("### 최근 팀원 진행·설정 공유 (Discord 연동)")
    if not shares:
        lines.append("- 아직 공유된 진행 내역이 없습니다.")
    else:
        for item in shares[:10]:
            ak = f"({item['access_key']})" if item.get("access_key") else ""
            dc = " · Discord전송됨" if item.get("discord_sent") else ""
            lines.append(
                f"- **[{item.get('status_label') or item.get('status')}]** `{item.get('area')}` — "
                f"**{item.get('title')}** ({item.get('author')}{ak}, {_fmt_ts(item.get('ts', 0))}{dc})"
            )
            lines.append(f"  - 내용: {item.get('summary', '')}")
            if item.get("check_request"):
                lines.append(f"  - 확인요청: {item['check_request']}")
            if item.get("cfg_url"):
                lines.append(f"  - 웹링크: {item['cfg_url']}")

    if changes:
        lines.append("\n### 최근 위키 구성 변경 이력")
        for c in changes[:8]:
            ak = f"({c['access_key']})" if c.get("access_key") else ""
            who = c.get("matched_user") or c.get("author") or "-"
            lines.append(
                f"- `{c.get('kind')}` **{c.get('title') or c.get('doc_id')}** r{c.get('rev')} "
                f"by {who}{ak}: {c.get('message') or '-'}"
            )
    return "\n".join(lines)


def build_ai_feed(r, s: auth.Session, limit: int = 15, area: str = "") -> dict[str, Any]:
    shares = list_shares(r, s.team_id, limit=limit, area=area)
    changes = docs.list_changes(r, s, limit=min(max(1, int(limit or 15)), 15))
    return {
        "team": {"slug": s.slug, "name": s.team_name},
        "viewer": {"member": s.member, "access_key": s.access_key},
        "infra_ref_url": "https://figteam.ktci5.kr/md/v1",
        "share_ui_url": "https://figteam.ktci5.kr/api/ai/share-ui",
        "discord_configured": bool(os.environ.get("FIGTEAM_DISCORD_WEBHOOK_URL", "").strip()),
        "shares": shares,
        "recent_wiki_changes": changes,
        "markdown_brief": build_markdown_brief(s.slug, shares, changes, include_header=True),
    }


def build_internal_feed(r, team_slug: str = "figteam", limit: int = 10) -> dict[str, Any]:
    t = r.hgetall(f"fw:team:{team_slug}")
    if not t or not t.get("id"):
        return {"team": team_slug, "shares": [], "markdown_section": ""}
    team_id = int(t["id"])
    shares = list_shares(r, team_id, limit=limit)
    if not shares:
        return {"team": team_slug, "shares": [], "markdown_section": ""}
    md = "## 5. 최신 팀 진행상황 및 설정 공유 (Discord 연동)\n\n" + build_markdown_brief(
        team_slug, shares, [], include_header=False
    )
    return {"team": team_slug, "shares": shares, "markdown_section": md}


def build_openapi_spec(base_url: str = "https://figteam.ktci5.kr") -> dict[str, Any]:
    base = (base_url or "https://figteam.ktci5.kr").rstrip("/")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "FIGTEAM 하이브리드 인프라 협업 & Discord 공유 커넥터 API",
            "version": "1.0.0",
            "description": (
                "MCP·별도 AI API 없이 ChatGPT Custom GPT 등에서 figteam 웹 로그인(OAuth 2.0)으로 "
                "팀 진행상황·설정 공유 내역을 상호 조회하고 Discord 채널에 전송합니다."
            ),
        },
        "servers": [{"url": base}],
        "security": [{"figteamOAuth": ["read", "write"]}],
        "paths": {
            "/api/ai/feed": {
                "get": {
                    "operationId": "getTeamFeed",
                    "summary": "팀 최신 진행상황·설정 공유 및 위키 변경 이력 조회",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50},
                        },
                        {
                            "name": "area",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "인스턴스/영역 필터 (예: db01, ktedge, cp1, awsdr)",
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "공유 피드 및 markdown_brief",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
            "/api/ai/share": {
                "post": {
                    "operationId": "shareTeamUpdate",
                    "summary": "진행상황·설정 변경 내용을 팀 피드에 기록하고 Discord 채널로 전송",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["summary"],
                                    "properties": {
                                        "area": {"type": "string", "description": "예: inst-db01/mysql, inst-ktedge/nginx"},
                                        "status": {
                                            "type": "string",
                                            "enum": ["in_progress", "done", "check_needed", "incident", "info"],
                                            "default": "info",
                                        },
                                        "title": {"type": "string", "description": "한 줄 제목 (최대 120자)"},
                                        "summary": {"type": "string", "description": "변경·확인 내용 요약 (비밀값 포함 금지)"},
                                        "check_request": {"type": "string", "description": "다른 팀원에게 요청할 교차 확인 사항"},
                                        "cfg_url": {"type": "string", "description": "관련 #cfg 공식 웹 URL"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "공유 저장 및 Discord Webhook 발송 결과",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "figteamOAuth": {
                    "type": "oauth2",
                    "flows": {
                        "authorizationCode": {
                            "authorizationUrl": f"{base}/api/ai/oauth/authorize",
                            "tokenUrl": f"{base}/api/ai/oauth/token",
                            "scopes": {
                                "read": "팀 진행·설정 공유 피드 조회",
                                "write": "진행·설정 공유 등록 및 Discord 알림 전송",
                            },
                        }
                    },
                }
            }
        },
    }


_BASE_STYLE = """
  body { margin:0; background:#0b1220; color:#e2e8f0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; padding:24px 14px; }
  .wrap { max-width:760px; margin:0 auto; }
  .card { background:#111827; border:1px solid #263248; border-radius:12px; padding:22px; margin-bottom:16px; box-shadow:0 10px 30px rgba(0,0,0,.35); }
  h1 { font-size:20px; margin:0 0 8px; color:#fff; }
  h2 { font-size:16px; margin:0 0 12px; color:#fff; }
  .sub { font-size:13px; color:#94a3b8; line-height:1.55; margin:0 0 16px; }
  label { display:block; font-size:12px; font-weight:600; color:#cbd5e1; margin:12px 0 5px; }
  input, select, textarea { width:100%; box-sizing:border-box; background:#0f172a; border:1px solid #334155; color:#f8fafc; border-radius:8px; padding:10px 12px; font-size:13.5px; font-family:inherit; }
  textarea { min-height:110px; resize:vertical; line-height:1.5; }
  input:focus, select:focus, textarea:focus { outline:none; border-color:#3b82f6; }
  .row { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
  @media (max-width:640px) { .row { grid-template-columns:1fr; } }
  .btn { display:inline-flex; align-items:center; justify-content:center; gap:6px; border:0; border-radius:8px; padding:11px 16px; font-size:13.5px; font-weight:700; cursor:pointer; background:#2563eb; color:#fff; text-decoration:none; }
  .btn:hover { background:#1d4ed8; }
  .btn-sub { background:#1e293b; border:1px solid #334155; color:#e2e8f0; }
  .btn-sub:hover { border-color:#60a5fa; color:#fff; }
  .acts { display:flex; flex-wrap:wrap; gap:10px; margin-top:16px; align-items:center; }
  .pill { display:inline-block; padding:3px 9px; border-radius:999px; font-size:11.5px; font-weight:700; background:#1e293b; border:1px solid #334155; color:#93c5fd; }
  .alert { padding:11px 13px; border-radius:8px; font-size:13px; line-height:1.5; margin-bottom:14px; }
  .alert-err { background:rgba(239,68,68,.14); border:1px solid rgba(239,68,68,.45); color:#fecaca; }
  .alert-ok { background:rgba(16,185,129,.14); border:1px solid rgba(16,185,129,.45); color:#a7f3d0; }
  .alert-warn { background:rgba(245,158,11,.14); border:1px solid rgba(245,158,11,.45); color:#fde68a; }
  .feed-item { border:1px solid #1e293b; background:#0f172a; border-radius:8px; padding:12px; margin-bottom:10px; }
  .feed-top { display:flex; justify-content:space-between; gap:8px; flex-wrap:wrap; font-size:12px; color:#94a3b8; margin-bottom:6px; }
  .feed-title { font-weight:700; color:#f8fafc; font-size:14px; margin-bottom:4px; }
  .feed-body { font-size:13px; color:#cbd5e1; white-space:pre-wrap; line-height:1.5; }
"""


def render_oauth_authorize_html(
    session: auth.Session | None,
    params: dict[str, str],
    error: str = "",
    default_slug: str = "figteam",
) -> str:
    esc = html.escape
    cid = esc(params.get("client_id") or "")
    ruri = esc(params.get("redirect_uri") or "")
    state = esc(params.get("state") or "")
    scope = esc(params.get("scope") or "read write")
    slug = esc(default_slug)
    err_html = f'<div class="alert alert-err">{esc(error)}</div>' if error else ""

    if session:
        ak_pill = f' <span class="pill">{esc(session.access_key)}</span>' if session.access_key else ""
        auth_block = (
            f'<div class="alert alert-ok">현재 로그인됨: <b>{esc(session.member)}</b>{ak_pill} '
            f'(팀: <b>{esc(session.team_name)}</b>)</div>'
        )
        btn_label = "이 계정으로 AI 커넥터 연결 승인"
    else:
        auth_block = (
            '<div class="row">'
            f'<div><label>팀 주소</label><input type="text" name="slug" value="{slug}" readonly></div>'
            '<div><label>사용자 이름</label><input type="text" name="member" placeholder="예: 홍길동" maxlength="20" required></div>'
            '</div>'
            '<div class="row">'
            '<div><label>접속 키값 (영문·숫자 2~16자)</label><input type="text" name="access_key" placeholder="예: DEV01" maxlength="16" required></div>'
            '<div><label>팀 비밀번호</label><input type="password" name="password" placeholder="팀 비밀번호" required></div>'
            '</div>'
        )
        btn_label = "웹 로그인 후 AI 커넥터 연결 승인"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FIGTEAM AI 커넥터 로그인 승인</title>
  <style>{_BASE_STYLE}</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>🔗 FIGTEAM 웹 로그인 AI 커넥터 승인</h1>
      <p class="sub">MCP·별도 AI API 없이 AI 채팅(Custom GPT 등)에서 팀 진행상황 조회 및 Discord Webhook 공유를 허용합니다.</p>
      {err_html}
      <form method="post" action="/api/ai/oauth/approve">
        <input type="hidden" name="client_id" value="{cid}">
        <input type="hidden" name="redirect_uri" value="{ruri}">
        <input type="hidden" name="state" value="{state}">
        <input type="hidden" name="scope" value="{scope}">
        {auth_block}
        <p class="sub" style="margin-top:12px;">요청 권한: <span class="pill">{scope}</span> · 연결 대상: <code>{ruri}</code></p>
        <div class="acts">
          <button type="submit" class="btn">{btn_label}</button>
          <a class="btn btn-sub" href="/#cfg/overview">포털로 돌아가기</a>
        </div>
      </form>
    </div>
  </div>
</body>
</html>"""


def render_share_ui_html(
    session: auth.Session | None,
    prefill: dict[str, str],
    shares: list[dict[str, Any]],
    discord_configured: bool,
    error: str = "",
    notice: str = "",
    default_slug: str = "figteam",
) -> str:
    esc = html.escape
    err_html = f'<div class="alert alert-err">{esc(error)}</div>' if error else ""
    notice_html = f'<div class="alert alert-ok">{esc(notice)}</div>' if notice else ""
    dc_badge = (
        '<span class="pill">Discord Webhook 연결됨</span>'
        if discord_configured
        else '<span class="pill" style="color:#fde68a;">Discord Webhook 미설정 (팀 피드만 저장)</span>'
    )

    if session:
        ak = f' <span class="pill">{esc(session.access_key)}</span>' if session.access_key else ""
        login_fields = (
            f'<div class="alert alert-ok">로그인됨: <b>{esc(session.member)}</b>{ak} · {dc_badge}</div>'
        )
    else:
        login_fields = (
            '<div class="alert alert-warn">처음 1회 팀 로그인 정보를 입력하면 공유와 동시에 브라우저 세션이 유지됩니다.</div>'
            '<div class="row">'
            f'<div><label>팀 주소</label><input type="text" name="slug" value="{esc(default_slug)}" readonly></div>'
            '<div><label>사용자 이름</label><input type="text" name="member" placeholder="예: 홍길동" maxlength="20" required></div>'
            '</div>'
            '<div class="row">'
            '<div><label>접속 키값</label><input type="text" name="access_key" placeholder="예: DEV01" maxlength="16" required></div>'
            '<div><label>팀 비밀번호</label><input type="password" name="password" placeholder="팀 비밀번호" required></div>'
            '</div>'
        )

    cur_status = prefill.get("status") or "info"
    opts = []
    for k, (label, _) in STATUS_META.items():
        sel = " selected" if k == cur_status else ""
        opts.append(f'<option value="{esc(k)}"{sel}>{esc(label)} ({esc(k)})</option>')
    options_html = "".join(opts)

    feed_rows: list[str] = []
    for item in shares[:15]:
        ak_txt = f" ({esc(item['access_key'])})" if item.get("access_key") else ""
        dc_txt = " · Discord 전송됨" if item.get("discord_sent") else ""
        chk = (
            f'<div style="margin-top:6px;font-size:12px;color:#fde68a;">확인요청: {esc(item["check_request"])}</div>'
            if item.get("check_request")
            else ""
        )
        feed_rows.append(
            '<div class="feed-item">'
            f'<div class="feed-top"><span><span class="pill">{esc(item.get("status_label") or item.get("status") or "공유")}</span> '
            f'<code>{esc(item.get("area") or "general")}</code></span>'
            f'<span>{esc(item.get("author") or "게스트")}{ak_txt} · {_fmt_ts(item.get("ts", 0))}{dc_txt}</span></div>'
            f'<div class="feed-title">{esc(item.get("title") or "")}</div>'
            f'<div class="feed-body">{esc(item.get("summary") or "")}</div>'
            f"{chk}</div>"
        )
    feed_html = "".join(feed_rows) if feed_rows else '<p class="sub">로그인 후 또는 첫 공유 등록 시 최근 팀 진행 내역이 표시됩니다.</p>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FIGTEAM Discord · AI 1클릭 공유 브리지</title>
  <style>{_BASE_STYLE}</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>📣 FIGTEAM Discord · AI 1클릭 공유 브리지</h1>
      <p class="sub">Claude · Gemini · ChatGPT 채팅에서 정리한 진행상황·설정 변경을 팀 피드에 기록하고 Discord 채널로 즉시 공유합니다.</p>
      {err_html}{notice_html}
      <form method="post" action="/api/ai/share-ui">
        {login_fields}
        <div class="row">
          <div><label>영역 / 노드 (예: inst-db01/mysql, ktedge/nginx)</label><input type="text" name="area" value="{esc(prefill.get('area') or 'general')}" maxlength="60"></div>
          <div><label>진행 상태</label><select name="status">{options_html}</select></div>
        </div>
        <label>한 줄 제목</label>
        <input type="text" name="title" value="{esc(prefill.get('title') or '')}" placeholder="예: MySQL GTID 복제 지연 점검 완료" maxlength="120">
        <label>변경 · 확인 내용 요약 (비밀값·Webhook URL 입력 금지)</label>
        <textarea name="summary" required placeholder="AI 채팅에서 요약해준 내용을 붙여넣거나 확인하세요.">{esc(prefill.get('summary') or '')}</textarea>
        <div class="row">
          <div><label>타 영역 확인 요청 (선택)</label><input type="text" name="check_request" value="{esc(prefill.get('check_request') or '')}" placeholder="예: AWS DR ch_dr 상태 확인 부탁드립니다" maxlength="400"></div>
          <div><label>관련 #cfg 웹 URL (선택)</label><input type="text" name="cfg_url" value="{esc(prefill.get('cfg_url') or '')}" placeholder="https://figteam.ktci5.kr/#cfg/..." maxlength="300"></div>
        </div>
        <div class="acts">
          <button type="submit" class="btn">🚀 Discord 공유 + 팀 로그 저장</button>
          <button type="button" class="btn btn-sub" id="btn-copy-brief" onclick="copyBrief()">📋 AI 확인용 최신 현황 복사</button>
          <a class="btn btn-sub" href="/#cfg/overview">포털로 이동</a>
        </div>
      </form>
    </div>
    <div class="card">
      <h2>최근 팀 공유 피드</h2>
      {feed_html}
    </div>
  </div>
  <script>
    async function copyBrief() {{
      const btn = document.getElementById('btn-copy-brief');
      try {{
        const res = await fetch('/api/ai/feed?limit=15', {{ credentials: 'same-origin' }});
        if (!res.ok) throw new Error('로그인이 필요합니다 (' + res.status + ')');
        const data = await res.json();
        await navigator.clipboard.writeText(data.markdown_brief || '');
        btn.textContent = '✅ 복사 완료! AI 채팅창에 붙여넣기 하세요';
        setTimeout(() => {{ btn.textContent = '📋 AI 확인용 최신 현황 복사'; }}, 2500);
      }} catch (e) {{
        alert(e.message || '복사에 실패했습니다. 먼저 공유 또는 로그인을 진행해 주세요.');
      }}
    }}
  </script>
</body>
</html>"""
