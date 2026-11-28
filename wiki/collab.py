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
GOAL_LIMIT = 100
OAUTH_CODE_TTL = 300
OAUTH_TOKEN_TTL = 30 * 24 * 3600

STATUS_META: dict[str, tuple[str, int]] = {
    "in_progress": ("진행중", 0x3B82F6),
    "done": ("완료", 0x10B981),
    "check_needed": ("확인필요", 0xF59E0B),
    "incident": ("장애/이슈", 0xEF4444),
    "info": ("공유", 0x64748B),
}

GOAL_STATUS_META: dict[str, tuple[str, int]] = {
    "todo": ("대기", 0x64748B),
    "in_progress": ("진행중", 0x3B82F6),
    "blocked": ("블로커", 0xEF4444),
    "done": ("달성완료", 0x10B981),
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
        "k3s cp1/w1 노드 상태 및 6443/flannel(10.42.0.0/16) 통신 영향 확인 필요",
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
    if entry.get("goal_id"):
        g_lbl = entry.get("goal_title") or f"#{entry['goal_id']}"
        fields.append({"name": "연계 공동 목표", "value": f"#{entry['goal_id']} {g_lbl}"[:200], "inline": False})
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


def _parse_optional_int(val: Any) -> int | None:
    if val in (None, "", 0, "0"):
        return None
    try:
        n = int(val)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def list_goals(r, team_id: int, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), GOAL_LIMIT))
    raw_map = r.hgetall(f"fw:goals:{team_id}")
    if not raw_map:
        return []
    ordered_ids = [x for x in r.lrange(f"fw:goalorder:{team_id}", 0, GOAL_LIMIT - 1)]
    seen: set[str] = set()
    goals: list[dict[str, Any]] = []
    for gid in ordered_ids + sorted(raw_map.keys(), key=lambda x: int(x) if str(x).isdigit() else 0, reverse=True):
        if gid in seen or gid not in raw_map:
            continue
        seen.add(gid)
        try:
            goals.append(json.loads(raw_map[gid]))
        except ValueError:
            continue
        if len(goals) >= limit:
            break
    return goals


def summarize_goals(goals: list[dict[str, Any]]) -> dict[str, int]:
    total = len(goals)
    counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    for g_item in goals:
        st = g_item.get("status") or "todo"
        counts[st if st in counts else "todo"] += 1
    percent = int(round((counts["done"] / total) * 100)) if total else 0
    return {"total": total, **counts, "percent": percent}


def format_goal_embed(goal: dict[str, Any], summary: dict[str, int], action: str = "update") -> dict[str, Any]:
    st_key = goal.get("status") or "todo"
    label, color = GOAL_STATUS_META.get(st_key, GOAL_STATUS_META["todo"])
    who = f"{goal.get('updated_by') or '게스트'} ({goal['access_key']})" if goal.get("access_key") else (goal.get("updated_by") or "게스트")
    verb = "등록" if action == "create" else "갱신"
    fields: list[dict[str, Any]] = [
        {"name": "영역", "value": f"`{goal.get('area') or 'general'}`", "inline": True},
        {"name": "담당자", "value": goal.get("owner") or who, "inline": True},
        {"name": "전체 달성률", "value": f"{summary['done']}/{summary['total']} ({summary['percent']}%)", "inline": True},
    ]
    if goal.get("target_date"):
        fields.append({"name": "목표 기한", "value": goal["target_date"], "inline": True})
    if goal.get("cfg_url"):
        fields.append({"name": "관련 #cfg", "value": goal["cfg_url"], "inline": False})
    return {
        "username": "FIGTEAM 공동 목표 보드",
        "embeds": [
            {
                "title": f"[목표 {label} · {verb}] #{goal['id']} {goal.get('title', '')}"[:250],
                "description": (goal.get("note") or "팀 공동 목표 타겟이 업데이트되었습니다.")[:1500],
                "color": color,
                "fields": fields[:10],
                "footer": {"text": f"작성/변경: {who} · https://figteam.ktci5.kr/api/ai/hub"},
            }
        ],
    }


def upsert_goal(r, s: auth.Session, data: dict[str, Any], send_discord: bool = True) -> dict[str, Any]:
    gid = _parse_optional_int(data.get("goal_id") or data.get("id"))
    goals_key = f"fw:goals:{s.team_id}"
    order_key = f"fw:goalorder:{s.team_id}"
    ts = int(time.time())

    if gid:
        raw_prev = r.hget(goals_key, str(gid))
        if not raw_prev:
            raise ApiError(404, f"공동 목표 #{gid} 를 찾을 수 없습니다")
        prev = json.loads(raw_prev)
        action = "update"
        title = _clean_text(data.get("title"), "title", 120, required=False, default=prev.get("title") or "")
        if not title:
            raise ApiError(422, "title 내용을 입력하세요", {"field": "title"})
        area = _clean_text(data.get("area"), "area", 60, required=False, default=prev.get("area") or "general")
        owner = _clean_text(data.get("owner"), "owner", 40, required=False, default=prev.get("owner") or s.member)
        st_raw = str(data.get("status") if data.get("status") not in (None, "") else (prev.get("status") or "todo")).strip().lower()
        status = st_raw if st_raw in GOAL_STATUS_META else "todo"
        target_date = _clean_text(data.get("target_date"), "target_date", 20, required=False, default=prev.get("target_date") or "")
        note = _clean_text(data.get("note"), "note", 600, required=False, default=prev.get("note") or "")
        cfg_url = _normalize_cfg_url(data.get("cfg_url")) if "cfg_url" in data else (prev.get("cfg_url") or "")
        created_at = int(prev.get("created_at") or ts)
    else:
        action = "create"
        gid = int(r.incr("fw:seq:goal"))
        title = _clean_text(data.get("title"), "title", 120, required=True)
        area = _clean_text(data.get("area"), "area", 60, required=False, default="general")
        owner = _clean_text(data.get("owner"), "owner", 40, required=False, default=s.member)
        st_raw = str(data.get("status") or "todo").strip().lower()
        status = st_raw if st_raw in GOAL_STATUS_META else "todo"
        target_date = _clean_text(data.get("target_date"), "target_date", 20, required=False, default="")
        note = _clean_text(data.get("note"), "note", 600, required=False, default="")
        cfg_url = _normalize_cfg_url(data.get("cfg_url"))
        created_at = ts

    goal: dict[str, Any] = {
        "id": gid,
        "title": title,
        "area": area,
        "owner": owner,
        "status": status,
        "status_label": GOAL_STATUS_META[status][0],
        "target_date": target_date,
        "note": note,
        "cfg_url": cfg_url,
        "updated_by": s.member,
        "access_key": s.access_key,
        "created_at": created_at,
        "updated_at": ts,
    }

    p = r.pipeline()
    p.hset(goals_key, str(gid), json.dumps(goal, ensure_ascii=False))
    if action == "create":
        p.lpush(order_key, str(gid))
        p.ltrim(order_key, 0, GOAL_LIMIT - 1)
    p.execute()

    if s.access_key:
        auth.record_access(r, s.team_id, s.member, s.access_key, "goal", detail=f"#{gid} [{GOAL_STATUS_META[status][0]}] {title[:50]}")

    all_goals = list_goals(r, s.team_id, limit=GOAL_LIMIT)
    summary = summarize_goals(all_goals)
    discord_res: dict[str, Any] = {"sent": False, "reason": "skipped"}
    if send_discord:
        discord_res = send_discord_webhook(format_goal_embed(goal, summary, action=action))

    return {"ok": True, "goal": goal, "summary": summary, "discord": discord_res}


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

    goal_id = _parse_optional_int(data.get("goal_id"))
    goal_title = ""
    updated_goal: dict[str, Any] | None = None
    if goal_id:
        raw_g = r.hget(f"fw:goals:{s.team_id}", str(goal_id))
        if raw_g:
            try:
                g_obj = json.loads(raw_g)
                goal_title = g_obj.get("title") or ""
            except ValueError:
                goal_id = None
        else:
            goal_id = None

    goal_status_raw = str(data.get("goal_status") or "").strip().lower()
    if goal_id and goal_status_raw in GOAL_STATUS_META:
        g_res = upsert_goal(r, s, {"goal_id": goal_id, "status": goal_status_raw}, send_discord=False)
        updated_goal = g_res["goal"]
        goal_title = updated_goal.get("title") or goal_title

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
        "goal_id": goal_id,
        "goal_title": goal_title,
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

    out: dict[str, Any] = {
        "ok": True,
        "share": entry,
        "discord": discord_res,
        "crosscheck_hints": hints,
    }
    if updated_goal:
        out["goal"] = updated_goal
    return out


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
    goals: list[dict[str, Any]] | None = None,
    include_header: bool = True,
) -> str:
    lines: list[str] = []
    goals_list = goals or []
    gs = summarize_goals(goals_list)
    if include_header:
        lines.append(f"## FIGTEAM ({team_slug}) 공동 목표 · 최신 팀 진행상황")
        lines.append("> 인프라 기준표: https://figteam.ktci5.kr/md/v1 | 통합 허브(GPT·Claude·Gemini · Discord): https://figteam.ktci5.kr/api/ai/hub\n")

    if goals_list:
        lines.append(f"### 공동 목표 · 타겟 현황 (달성 {gs['done']}/{gs['total']} · {gs['percent']}%)")
        for g_item in goals_list[:15]:
            due = f", 기한 {g_item['target_date']}" if g_item.get("target_date") else ""
            lines.append(
                f"- **#{g_item['id']} [{g_item.get('status_label') or g_item.get('status')}]** "
                f"`{g_item.get('area')}` **{g_item.get('title')}** (담당: {g_item.get('owner') or '-'}{due})"
            )
            if g_item.get("note"):
                lines.append(f"  - 메모: {g_item['note']}")
        lines.append("")

    lines.append("### 최근 팀원 진행·설정 공유 (Discord 연동)")
    if not shares:
        lines.append("- 아직 공유된 진행 내역이 없습니다.")
    else:
        for item in shares[:10]:
            ak = f"({item['access_key']})" if item.get("access_key") else ""
            dc = " · Discord전송됨" if item.get("discord_sent") else ""
            g_ref = f" · 목표 #{item['goal_id']}" if item.get("goal_id") else ""
            lines.append(
                f"- **[{item.get('status_label') or item.get('status')}]** `{item.get('area')}` — "
                f"**{item.get('title')}** ({item.get('author')}{ak}, {_fmt_ts(item.get('ts', 0))}{g_ref}{dc})"
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


def build_ai_launch_prompt(
    team_slug: str,
    viewer_member: str,
    viewer_key: str,
    goals: list[dict[str, Any]],
    shares: list[dict[str, Any]],
    changes: list[dict[str, Any]],
    focus_goal_id: int | None = None,
) -> tuple[str, str]:
    gs = summarize_goals(goals)
    who = f"{viewer_member} ({viewer_key})" if viewer_key else viewer_member
    focus_goal = next((g_item for g_item in goals if g_item.get("id") == focus_goal_id), None) if focus_goal_id else None

    lines = [
        f"[FIGTEAM ({team_slug}) AI 협업 브리핑 — MCP·AI API 미사용 / GPT·Claude·Gemini 공통]",
        f"작업자: {who}",
        f"공동 목표 달성률: {gs['done']}/{gs['total']} ({gs['percent']}%) | 진행중 {gs['in_progress']} · 블로커 {gs['blocked']}",
    ]
    if focus_goal:
        lines.append(
            f"★ 현재 집중 목표: #{focus_goal['id']} [{focus_goal.get('status_label')}] "
            f"{focus_goal.get('title')} (영역: {focus_goal.get('area')}, 담당: {focus_goal.get('owner')})"
        )
        if focus_goal.get("note"):
            lines.append(f"  메모: {focus_goal['note']}")

    lines.append("\n[공동 목표 보드]")
    if goals:
        for g_item in goals[:10]:
            lines.append(f"- #{g_item['id']} [{g_item.get('status_label')}] ({g_item.get('area')}) {g_item.get('title')} / 담당: {g_item.get('owner')}")
    else:
        lines.append("- 등록된 공동 목표가 없습니다. (허브 https://figteam.ktci5.kr/api/ai/hub 에서 추가 가능)")

    lines.append("\n[인프라 핵심 실측 기준 (SSOT: https://figteam.ktci5.kr/md/v1)]")
    lines.append("- OpenStack: Controller 192.168.120.160(14GB), Compute1·3·4(각 8GB), vmnet8 192.168.120.0/24, app-net 172.20.0.0/24, data-net 10.10.2.0/24")
    lines.append("- k3s(v1.37.2+k3s1): cp1 172.20.0.86(FIP .226, NodePort 30080), w1 172.20.0.180, flannel VXLAN, Pod CIDR 10.42.0.0/16, Svc 10.43.0.0/16")
    lines.append("- DB/KT/AWS: Primary MySQL 10.10.2.10:3306(GTID ON) -> AWS DR 10.51.1.165(Warm-Standby ch_dr), KT Edge 14.63.212.190(Nginx WAF + WG 10.200.0.1)")
    lines.append("- 원칙: s1 물리 조작 금지, 실제 변경은 #cfg 웹 포털([👁️ 뷰 모드] -> 빨강색 [✏️ 수정/변경]) 링크 안내, 비밀값·Webhook 평문 출력 금지")

    lines.append("\n[최근 팀원 진행·설정 공유]")
    if shares:
        for s_item in shares[:5]:
            lines.append(f"- [{s_item.get('status_label')}] {s_item.get('area')} | {s_item.get('title')} (by {s_item.get('author')}): {s_item.get('summary', '')[:180]}")
    else:
        lines.append("- 최근 공유 내역 없음")

    if changes:
        lines.append("\n[최근 위키 변경]")
        for c in changes[:3]:
            lines.append(f"- {c.get('kind')} {c.get('title') or c.get('doc_id')} r{c.get('rev')} by {c.get('matched_user') or c.get('author')}: {c.get('message') or '-'}")

    lines.append("\n[응답 및 Discord 공유 지침]")
    lines.append("1. 위 공동 목표와 최근 팀원 변경사항 충돌 여부를 먼저 점검해 답하라.")
    lines.append("2. 작업·분석이 끝나면 영역/상태/제목/내용/확인요청을 정리하고, OAuth 커넥터가 있으면 shareTeamUpdate·upsertTeamGoal을 호출하고, 없으면 아래 1클릭 Discord 반영 링크를 생성하라:")
    g_param = f"goal_id={focus_goal['id']}&" if focus_goal else ""
    lines.append(f"   https://figteam.ktci5.kr/api/ai/hub?{g_param}area=<영역>&status=<in_progress|done|check_needed|incident>&title=<제목>&summary=<요약>&check=<확인요청>")
    full_prompt = "\n".join(lines)

    short_lines = [
        f"FIGTEAM({team_slug}) 공동목표 협업 | 작업자:{who} | 목표달성:{gs['done']}/{gs['total']}({gs['percent']}%)",
        f"집중목표: #{focus_goal['id']} [{focus_goal.get('status_label')}] {focus_goal.get('title')}" if focus_goal else (f"주요목표: " + ", ".join(f"#{x['id']}[{x.get('status_label')}]{x.get('title')[:24]}" for x in goals[:3]) if goals else "공동목표 미등록"),
        "인프라기준: OpenStack(192.168.120.0/24), k3s(cp1 .86/w1 .180, flannel 10.42.0.0/16, NodePort 30080), MySQL(10.10.2.10 GTID)->AWS DR(10.51.1.165), KT Edge(14.63.212.190, WG 10.200.0.1), s1직접조작금지",
        f"완료후회신링크: https://figteam.ktci5.kr/api/ai/hub?{g_param}area=<영역>&status=<상태>&title=<제목>&summary=<요약>",
        "먼저 위 목표 기준으로 현재 작업을 도와줘.",
    ]
    return full_prompt, "\n".join(short_lines)


def build_ai_feed(r, s: auth.Session, limit: int = 15, area: str = "") -> dict[str, Any]:
    shares = list_shares(r, s.team_id, limit=limit, area=area)
    changes = docs.list_changes(r, s, limit=min(max(1, int(limit or 15)), 15))
    goals = list_goals(r, s.team_id, limit=50)
    goal_summary = summarize_goals(goals)
    full_prompt, short_prompt = build_ai_launch_prompt(s.slug, s.member, s.access_key, goals, shares, changes)
    return {
        "team": {"slug": s.slug, "name": s.team_name},
        "viewer": {"member": s.member, "access_key": s.access_key},
        "infra_ref_url": "https://figteam.ktci5.kr/md/v1",
        "hub_url": "https://figteam.ktci5.kr/api/ai/hub",
        "share_ui_url": "https://figteam.ktci5.kr/api/ai/share-ui",
        "discord_configured": bool(os.environ.get("FIGTEAM_DISCORD_WEBHOOK_URL", "").strip()),
        "goals": goals,
        "goal_summary": goal_summary,
        "shares": shares,
        "recent_wiki_changes": changes,
        "markdown_brief": build_markdown_brief(s.slug, shares, changes, goals=goals, include_header=True),
        "ai_launch_prompt": full_prompt,
        "ai_short_prompt": short_prompt,
    }


def build_internal_feed(r, team_slug: str = "figteam", limit: int = 10) -> dict[str, Any]:
    t = r.hgetall(f"fw:team:{team_slug}")
    if not t or not t.get("id"):
        return {"team": team_slug, "goals": [], "shares": [], "markdown_section": ""}
    team_id = int(t["id"])
    goals = list_goals(r, team_id, limit=20)
    shares = list_shares(r, team_id, limit=limit)
    if not shares and not goals:
        return {"team": team_slug, "goals": [], "shares": [], "markdown_section": ""}
    md = "## 5. 최신 팀 공동 목표 · 진행상황 및 설정 공유 (Discord 연동)\n\n" + build_markdown_brief(
        team_slug, shares, [], goals=goals, include_header=False
    )
    return {"team": team_slug, "goals": goals, "shares": shares, "markdown_section": md}


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
            "/api/ai/goals": {
                "get": {
                    "operationId": "getTeamGoals",
                    "summary": "팀 공동 목표·타겟 보드 및 달성률 조회",
                    "responses": {
                        "200": {
                            "description": "공동 목표 목록 및 달성률 요약",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                },
                "post": {
                    "operationId": "upsertTeamGoal",
                    "summary": "공동 목표 신규 생성 또는 상태/내용 갱신 (Discord 보드 알림 발송)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "goal_id": {"type": "integer", "description": "기존 목표 수정 시 ID, 신규 시 생략"},
                                        "title": {"type": "string", "description": "공동 목표 제목 (신규 시 필수)"},
                                        "area": {"type": "string", "description": "예: inst-cp1/k8s, inst-db01/mysql"},
                                        "owner": {"type": "string", "description": "담당자 이름"},
                                        "status": {
                                            "type": "string",
                                            "enum": ["todo", "in_progress", "blocked", "done"],
                                            "default": "todo",
                                        },
                                        "target_date": {"type": "string", "description": "목표 기한 (예: 2026-11-30)"},
                                        "note": {"type": "string", "description": "목표 완료 기준 또는 메모"},
                                        "cfg_url": {"type": "string", "description": "관련 #cfg 웹 URL"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "목표 저장 및 Discord 알림 결과",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    },
                },
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
                                        "goal_id": {"type": "integer", "description": "연계할 공동 목표 ID (선택)"},
                                        "goal_status": {
                                            "type": "string",
                                            "enum": ["todo", "in_progress", "blocked", "done"],
                                            "description": "공유와 함께 공동 목표 상태도 변경할 때 지정",
                                        },
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


def render_collab_hub_html(
    session: auth.Session | None,
    prefill: dict[str, str],
    shares: list[dict[str, Any]],
    discord_configured: bool,
    goals: list[dict[str, Any]] | None = None,
    ai_prompts: tuple[str, str] = ("", ""),
    error: str = "",
    notice: str = "",
    default_slug: str = "figteam",
) -> str:
    esc = html.escape
    goals_list = goals or []
    gs = summarize_goals(goals_list)
    err_html = f'<div class="alert alert-err">{esc(error)}</div>' if error else ""
    notice_html = f'<div class="alert alert-ok">{esc(notice)}</div>' if notice else ""
    dc_badge = (
        '<span class="pill">Discord Webhook 연결됨</span>'
        if discord_configured
        else '<span class="pill" style="color:#fde68a;">Discord Webhook 미설정</span>'
    )

    if session:
        ak = f' <span class="pill">{esc(session.access_key)}</span>' if session.access_key else ""
        login_banner = (
            f'<div class="alert alert-ok">통합 로그인됨: <b>{esc(session.member)}</b>{ak} · '
            f'팀 <b>{esc(session.team_name)}</b> · {dc_badge}</div>'
        )
        inline_login = ""
    else:
        login_banner = (
            f'<div class="alert alert-warn">MCP·AI API 없이 GPT · Claude · Gemini 에서 공통 목표를 공유하려면 '
            f'아래 팀 로그인(1회)으로 연결하세요. · {dc_badge}</div>'
        )
        inline_login = (
            '<div class="row">'
            f'<div><label>팀 주소</label><input type="text" name="slug" value="{esc(default_slug)}" readonly></div>'
            '<div><label>사용자 이름</label><input type="text" name="member" placeholder="예: 홍길동" maxlength="20" required></div>'
            '</div>'
            '<div class="row">'
            '<div><label>접속 키값</label><input type="text" name="access_key" placeholder="예: DEV01" maxlength="16" required></div>'
            '<div><label>팀 비밀번호</label><input type="password" name="password" placeholder="팀 비밀번호" required></div>'
            '</div>'
        )

    focus_gid = str(prefill.get("goal_id") or "")
    goal_sel_opts = ['<option value="">전체 공동 목표 기준</option>']
    for g_item in goals_list:
        sel = " selected" if str(g_item["id"]) == focus_gid else ""
        goal_sel_opts.append(
            f'<option value="{g_item["id"]}"{sel}>#{g_item["id"]} [{esc(g_item.get("status_label") or "")}] {esc(g_item.get("title") or "")}</option>'
        )
    goal_select_html = "".join(goal_sel_opts)

    goal_cards: list[str] = []
    for g_item in goals_list[:20]:
        st_k = g_item.get("status") or "todo"
        st_lbl = g_item.get("status_label") or GOAL_STATUS_META.get(st_k, ("대기", 0))[0]
        due = f' · 기한 {esc(g_item["target_date"])}' if g_item.get("target_date") else ""
        note_html = f'<div class="feed-body" style="margin-bottom:8px;">{esc(g_item["note"])}</div>' if g_item.get("note") else ""
        st_btns: list[str] = []
        if session:
            for k_btn, (lbl_btn, _) in GOAL_STATUS_META.items():
                active_cls = " btn" if k_btn == st_k else " btn btn-sub"
                st_btns.append(
                    f'<form method="post" action="/api/ai/hub/goal-status" style="display:inline;">'
                    f'<input type="hidden" name="goal_id" value="{g_item["id"]}">'
                    f'<input type="hidden" name="status" value="{esc(k_btn)}">'
                    f'<button type="submit" class="{active_cls}" style="padding:5px 10px;font-size:12px;">{esc(lbl_btn)}</button>'
                    f'</form>'
                )
        goal_cards.append(
            '<div class="feed-item">'
            f'<div class="feed-top"><span><span class="pill">#{g_item["id"]} {esc(st_lbl)}</span> '
            f'<code>{esc(g_item.get("area") or "general")}</code></span>'
            f'<span>담당: {esc(g_item.get("owner") or "-")}{due}</span></div>'
            f'<div class="feed-title">{esc(g_item.get("title") or "")}</div>'
            f'{note_html}'
            f'<div class="acts" style="margin-top:6px;">{"".join(st_btns)}</div>'
            '</div>'
        )
    goals_board_html = "".join(goal_cards) if goal_cards else '<p class="sub">아직 등록된 공동 목표가 없습니다. 아래에서 첫 목표를 등록하세요.</p>'

    cur_status = prefill.get("status") or "info"
    opts = []
    for k, (label, _) in STATUS_META.items():
        sel = " selected" if k == cur_status else ""
        opts.append(f'<option value="{esc(k)}"{sel}>{esc(label)} ({esc(k)})</option>')
    options_html = "".join(opts)

    cur_goal_st = prefill.get("goal_status") or ""
    g_st_opts = ['<option value="">목표 상태 변경 안 함</option>']
    for k, (label, _) in GOAL_STATUS_META.items():
        sel = " selected" if k == cur_goal_st else ""
        g_st_opts.append(f'<option value="{esc(k)}"{sel}>연계 목표를 [{esc(label)}]로 변경</option>')

    feed_rows: list[str] = []
    for item in shares[:15]:
        ak_txt = f" ({esc(item['access_key'])})" if item.get("access_key") else ""
        dc_txt = " · Discord 전송됨" if item.get("discord_sent") else ""
        g_badge = f' <span class="pill">목표 #{item["goal_id"]}</span>' if item.get("goal_id") else ""
        chk = (
            f'<div style="margin-top:6px;font-size:12px;color:#fde68a;">확인요청: {esc(item["check_request"])}</div>'
            if item.get("check_request")
            else ""
        )
        feed_rows.append(
            '<div class="feed-item">'
            f'<div class="feed-top"><span><span class="pill">{esc(item.get("status_label") or item.get("status") or "공유")}</span> '
            f'<code>{esc(item.get("area") or "general")}</code>{g_badge}</span>'
            f'<span>{esc(item.get("author") or "게스트")}{ak_txt} · {_fmt_ts(item.get("ts", 0))}{dc_txt}</span></div>'
            f'<div class="feed-title">{esc(item.get("title") or "")}</div>'
            f'<div class="feed-body">{esc(item.get("summary") or "")}</div>'
            f"{chk}</div>"
        )
    feed_html = "".join(feed_rows) if feed_rows else '<p class="sub">로그인 후 또는 첫 공유 등록 시 최근 팀 진행 내역이 표시됩니다.</p>'

    full_prompt_txt = esc(ai_prompts[0] or "")
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FIGTEAM GPT·Claude·Gemini 통합 협업 허브 &amp; Discord</title>
  <style>{_BASE_STYLE}
    .prog {{ height:8px; background:#0f172a; border:1px solid #334155; border-radius:999px; overflow:hidden; margin:8px 0 14px; }}
    .prog > span {{ display:block; height:100%; background:#10b981; }}
    .btn-gpt {{ background:#059669; }} .btn-gpt:hover {{ background:#047857; }}
    .btn-claude {{ background:#d97706; }} .btn-claude:hover {{ background:#b45309; }}
    .btn-gemini {{ background:#2563eb; }} .btn-gemini:hover {{ background:#1d4ed8; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>🎯 FIGTEAM GPT · Claude · Gemini 통합 로그인 &amp; Discord 협업 허브</h1>
      <p class="sub">MCP·별도 AI API 없이 웹 로그인 세션 하나로 3대 AI 채팅에 동일한 공동 목표·최신 현황을 연결하고 Discord로 결과를 공유합니다.</p>
      {err_html}{notice_html}{login_banner}
      <label for="hub-focus-goal">집중 공동 목표 선택 (3대 AI 런처 반영)</label>
      <select id="hub-focus-goal">{goal_select_html}</select>
      <div class="acts">
        <button type="button" class="btn btn-gpt" onclick="launchAi('chatgpt')">🟢 ChatGPT로 열기</button>
        <button type="button" class="btn btn-claude" onclick="launchAi('claude')">🟠 Claude로 열기</button>
        <button type="button" class="btn btn-gemini" onclick="launchAi('gemini')">🔵 Gemini로 열기</button>
        <button type="button" class="btn btn-sub" id="btn-copy-prompt" onclick="launchAi('copy')">📋 공통 프롬프트 복사 (Windows 앱용)</button>
      </div>
      <p id="hub-launch-msg" class="sub" style="margin-top:10px;margin-bottom:0;">버튼을 누르면 최신 공동 목표·팀 공유 브리핑이 클립보드에 자동 복사되며 해당 AI 채팅창이 열립니다. (ChatGPT Custom GPT OAuth 연결도 동시 지원)</p>
      <textarea id="hub-fallback-prompt" readonly style="margin-top:10px;min-height:80px;font-size:12px;color:#94a3b8;{'display:none;' if not full_prompt_txt else ''}">{full_prompt_txt}</textarea>
    </div>

    <div class="card">
      <h2>🏁 공동 목표 · 타겟 보드 (달성 {gs['done']}/{gs['total']} · {gs['percent']}%)</h2>
      <div class="prog"><span style="width:{gs['percent']}%"></span></div>
      {goals_board_html}
      <details style="margin-top:12px;">
        <summary style="cursor:pointer;font-weight:700;color:#93c5fd;font-size:13.5px;">+ 새 공동 목표 타겟 추가</summary>
        <form method="post" action="/api/ai/hub/goal" style="margin-top:10px;">
          {inline_login if not session else ''}
          <div class="row">
            <div><label>목표 제목</label><input type="text" name="title" placeholder="예: 3사 DR 자동 절체 리허설 완료" maxlength="120" required></div>
            <div><label>영역 / 노드</label><input type="text" name="area" value="{esc(prefill.get('area') or 'general')}" maxlength="60"></div>
          </div>
          <div class="row">
            <div><label>담당자</label><input type="text" name="owner" value="{esc(session.member if session else '')}" placeholder="예: 홍길동" maxlength="40"></div>
            <div><label>목표 기한 (선택)</label><input type="text" name="target_date" placeholder="예: 2026-11-30" maxlength="20"></div>
          </div>
          <label>완료 기준 · 메모 (선택)</label>
          <input type="text" name="note" placeholder="예: ch_dr 지연 0초 &amp; minwon.ktci5.kr 200 OK 확인" maxlength="600">
          <div class="acts"><button type="submit" class="btn">🎯 목표 등록 + Discord 알림</button></div>
        </form>
      </details>
    </div>

    <div class="card">
      <h2>📣 진행 · 설정 공유 등록 (Discord Webhook 실시간 전송)</h2>
      <form method="post" action="/api/ai/hub">
        {inline_login}
        <div class="row">
          <div><label>영역 / 노드</label><input type="text" name="area" value="{esc(prefill.get('area') or 'general')}" maxlength="60"></div>
          <div><label>진행 상태</label><select name="status">{options_html}</select></div>
        </div>
        <div class="row">
          <div><label>연계 공동 목표 (선택)</label><select name="goal_id">{goal_select_html}</select></div>
          <div><label>연계 목표 상태 함께 변경</label><select name="goal_status">{"".join(g_st_opts)}</select></div>
        </div>
        <label>한 줄 제목</label>
        <input type="text" name="title" value="{esc(prefill.get('title') or '')}" placeholder="예: k3s flannel 10.42.0.0/16 점검 완료" maxlength="120">
        <label>변경 · 확인 내용 요약 (비밀값·Webhook URL 입력 금지)</label>
        <textarea name="summary" required placeholder="GPT·Claude·Gemini 채팅에서 정리한 내용을 붙여넣으세요.">{esc(prefill.get('summary') or '')}</textarea>
        <div class="row">
          <div><label>타 영역 확인 요청 (선택)</label><input type="text" name="check_request" value="{esc(prefill.get('check_request') or '')}" placeholder="예: AWS DR 담당자 ch_dr 확인 부탁드립니다" maxlength="400"></div>
          <div><label>관련 #cfg 웹 URL (선택)</label><input type="text" name="cfg_url" value="{esc(prefill.get('cfg_url') or '')}" placeholder="https://figteam.ktci5.kr/#cfg/..." maxlength="300"></div>
        </div>
        <div class="acts">
          <button type="submit" class="btn">🚀 Discord 공유 + 팀 로그 저장</button>
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
    async function launchAi(target) {{
      const msgEl = document.getElementById('hub-launch-msg');
      const goalSel = document.getElementById('hub-focus-goal');
      const gid = goalSel ? goalSel.value : '';
      let fullPrompt = document.getElementById('hub-fallback-prompt')?.value || '';
      let shortPrompt = fullPrompt.slice(0, 900);
      try {{
        const res = await fetch('/api/ai/prompt' + (gid ? '?goal_id=' + encodeURIComponent(gid) : ''), {{ credentials: 'same-origin', cache: 'no-store' }});
        if (!res.ok) throw new Error('먼저 아래 팀 로그인(1회)을 완료해 주세요.');
        const data = await res.json();
        fullPrompt = data.prompt || fullPrompt;
        shortPrompt = data.short_prompt || shortPrompt;
        const fb = document.getElementById('hub-fallback-prompt');
        if (fb) {{ fb.value = fullPrompt; fb.style.display = 'block'; }}
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          await navigator.clipboard.writeText(fullPrompt);
        }}
      }} catch (e) {{
        msgEl.textContent = '⚠️ ' + (e.message || '로그인이 필요합니다.');
        return;
      }}
      if (target === 'copy') {{
        msgEl.textContent = '✅ 최신 공동 목표·인프라 공통 프롬프트를 복사했습니다. ChatGPT/Claude/Gemini 앱에 붙여넣으세요.';
        return;
      }}
      const q = encodeURIComponent(shortPrompt);
      if (target === 'chatgpt') {{
        window.open('https://chatgpt.com/?q=' + q, '_blank', 'noopener');
        msgEl.textContent = '✅ 전체 프롬프트도 클립보드에 복사했습니다. 필요 시 ChatGPT 창에 바로 붙여넣기 하세요.';
      }} else if (target === 'claude') {{
        window.open('https://claude.ai/new?q=' + q, '_blank', 'noopener');
        msgEl.textContent = '✅ 전체 프롬프트도 클립보드에 복사했습니다. 필요 시 Claude 창에 바로 붙여넣기 하세요.';
      }} else if (target === 'gemini') {{
        window.open('https://gemini.google.com/app', '_blank', 'noopener');
        msgEl.textContent = '✅ Gemini 창을 열었습니다! 클립보드에 전체 브리핑이 복사되었으니 Ctrl+V로 붙여넣어 시작하세요.';
      }}
    }}
  </script>
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
    return render_collab_hub_html(
        session=session,
        prefill=prefill,
        shares=shares,
        discord_configured=discord_configured,
        goals=[],
        ai_prompts=("", ""),
        error=error,
        notice=notice,
        default_slug=default_slug,
    )
