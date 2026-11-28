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
DISCORD_INBOX_LIMIT = 300
OAUTH_CODE_TTL = 300
OAUTH_TOKEN_TTL = 30 * 24 * 3600

DISCORD_CATEGORY_META: dict[str, tuple[str, int]] = {
    "task": ("처리할 과제", 0xF59E0B),
    "share": ("공유", 0x38BDF8),
}

DISCORD_TASK_STATUS_META: dict[str, str] = {
    "open": "미처리",
    "in_progress": "진행중",
    "done": "처리완료",
    "read": "확인됨",
}

DEFAULT_TRIGGER_TAGS = (
    "#figteaminfra",
    "@figteaminfra",
    "#figteam",
    "@figteam",
    "#인프라",
    "#과제",
    "#공유",
    "#장애",
    "#확인",
    "#요청",
)

_TASK_TAGS = {
    "과제", "할일", "todo", "task", "요청", "확인", "확인필요", "점검", "수정",
    "장애", "이슈", "긴급", "에러", "fix", "bug", "check", "incident", "action",
}
_SHARE_TAGS = {"공유", "참고", "완료", "공지", "info", "fyi", "done", "share", "notice"}

_TASK_KW_RE = re.compile(
    r"(해\s*주|부탁|확인\s*필요|확인\s*요청|점검\s*필요|수정\s*필요|처리\s*필요|조치\s*필요|"
    r"수정해|점검해|확인해|조치해|복구해|장애|오류|에러|실패|안\s*됨|안됨|끊김|멈춤|"
    r"\b(?:502|503|504|404|oom)\b|\?\s*$)",
    re.I,
)
_SHARE_KW_RE = re.compile(r"(공유드립니다|공유합니다|참고하세요|공지합니다|완료했습니다|완료됨|정상입니다|정상\s*동작)", re.I)

_AREA_HINTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(aws[\s-]?dr|10\.51|orchestrator|eks)", re.I), "inst-awsdr/dr"),
    (re.compile(r"(mysql|db[\s-]?01|gtid|binlog|3306)", re.I), "inst-db01/mysql"),
    (re.compile(r"(kt[\s-]?edge|ktedge|nginx|upstream|waf|ssl|tls)", re.I), "inst-ktedge/nginx"),
    (re.compile(r"(k3s|cp1|w1|flannel|pod|6443|argocd|kube)", re.I), "inst-cp1/k8s"),
    (re.compile(r"(wireguard|wg0|10\.200|vpn|mtu)", re.I), "network/wireguard"),
    (re.compile(r"(openstack|nova|neutron|compute|controller|fip|horizon)", re.I), "openstack/core"),
]

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


def send_discord_webhook(payload: dict[str, Any], webhook_url: str = "", wait: bool = True) -> dict[str, Any]:
    url = (webhook_url or os.environ.get("FIGTEAM_DISCORD_WEBHOOK_URL", "")).strip()
    if not url:
        return {"sent": False, "reason": "webhook_not_configured"}
    req_url = f"{url}{'&' if '?' in url else '?'}wait=true" if wait else url
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        req_url,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "figteam-collab/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp_body = resp.read().decode("utf-8") if resp.status == 200 else ""
            msg_id = ""
            if resp_body:
                try:
                    resp_json = json.loads(resp_body)
                    msg_id = str(resp_json.get("id") or "")
                except Exception:
                    pass
            return {"sent": 200 <= resp.status < 300, "status": resp.status, "message_id": msg_id}
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
    action_map = {
        "create": ("신규 생성", 0x10B981),
        "update": ("수정", 0x10B981),
        "delete": ("삭제", 0xEF4444),
        "restore": ("판 되돌리기", 0xF59E0B),
    }
    act_label, color = action_map.get(action, ("수정", 0x10B981))
    payload = {
        "username": "FIGTEAM 위키 알림",
        "embeds": [
            {
                "title": f"[위키 {act_label}] {doc_title or kind} (r{rev})"[:250],
                "description": (message or "구성 문서가 업데이트되었습니다.")[:1000],
                "color": color,
                "fields": [
                    {"name": "팀", "value": team_slug, "inline": True},
                    {"name": "문서 종류", "value": kind, "inline": True},
                    {"name": "작성자", "value": author_disp, "inline": True},
                    {"name": "웹 확인", "value": "https://figteam.ktci5.kr/#cfg/ · https://figteam.ktci5.kr/api/ai/hub", "inline": False},
                ],
                "footer": {"text": "https://figteam.ktci5.kr/#cfg/"},
            }
        ],
    }
    return send_discord_webhook(payload)


def has_figteam_trigger(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False
    extra = [x.strip().lower() for x in os.environ.get("FIGTEAM_DISCORD_TRIGGER_TAGS", "").split(",") if x.strip()]
    tags = DEFAULT_TRIGGER_TAGS + tuple(extra)
    return any(t in raw for t in tags) or "<@" in raw


def classify_discord_message(text: str, category_override: str = "") -> dict[str, Any]:
    raw = str(text or "").strip()
    hashtags = [m.group(1) for m in re.finditer(r"#([0-9A-Za-z가-힣_-]{1,40})", raw)]
    mentions = [m.group(0) for m in re.finditer(r"(?:@[0-9A-Za-z가-힣_-]{2,40}|<@!?\d+>)", raw)]
    tags_lower = [t.lower() for t in hashtags]

    ov = str(category_override or "").strip().lower()
    has_task_tag = any(t in _TASK_TAGS for t in tags_lower)
    has_share_tag = any(t in _SHARE_TAGS for t in tags_lower)
    has_task_kw = bool(_TASK_KW_RE.search(raw))
    has_share_kw = bool(_SHARE_KW_RE.search(raw))

    if ov in DISCORD_CATEGORY_META:
        category = ov
        reason = "수동 지정"
    elif has_task_tag:
        category = "task"
        reason = "과제/장애/요청 해시태그 감지"
    elif has_task_kw and not (has_share_tag and not has_task_tag and "?" not in raw):
        category = "task"
        reason = "조치/확인/오류 요청 표현 감지"
    elif has_share_tag or has_share_kw:
        category = "share"
        reason = "공유/완료/참고 표현 감지"
    else:
        category = "share"
        reason = "일반 공유 메시지 분류"

    area = "figteaminfra"
    for pat, guessed in _AREA_HINTS:
        if pat.search(raw):
            area = guessed
            break

    clean = re.sub(r"<@!?\d+>", "", raw)
    clean = re.sub(r"^(?:\s*[#@][0-9A-Za-z가-힣_-]+)+", "", clean).strip() or raw
    first_line = clean.splitlines()[0].strip() if clean else raw
    title = first_line[:100]
    hints = build_crosscheck_hints(area, clean)
    return {
        "category": category,
        "category_label": DISCORD_CATEGORY_META[category][0],
        "reason": reason,
        "hashtags": hashtags[:12],
        "mentions": mentions[:8],
        "area": area,
        "title": title,
        "clean_text": clean,
        "crosscheck_hints": hints,
    }


def format_discord_inbound_embed(entry: dict[str, Any], event_label: str = "웹 접수") -> dict[str, Any]:
    cat = entry.get("category") or "share"
    cat_label, color = DISCORD_CATEGORY_META.get(cat, DISCORD_CATEGORY_META["share"])
    st_label = DISCORD_TASK_STATUS_META.get(entry.get("task_status") or "", entry.get("task_status") or "-")
    fields: list[dict[str, Any]] = [
        {"name": "구분", "value": cat_label, "inline": True},
        {"name": "상태", "value": st_label, "inline": True},
        {"name": "영역", "value": f"`{entry.get('area') or 'figteaminfra'}`", "inline": True},
        {"name": "작성자", "value": entry.get("author") or "Discord", "inline": True},
    ]
    if entry.get("linked_goal_id"):
        fields.append({"name": "연계 공동 목표", "value": f"#{entry['linked_goal_id']}", "inline": True})
    fields.append({"name": "웹사이트 확인", "value": "https://figteam.ktci5.kr/api/ai/hub#discord-inbox", "inline": False})
    return {
        "username": "FIGTEAM Discord 브리지",
        "embeds": [
            {
                "title": f"[{event_label} · {cat_label}] {entry.get('title', '')}"[:250],
                "description": (entry.get("summary") or entry.get("raw_text") or "")[:1500],
                "color": color,
                "fields": fields[:10],
                "footer": {"text": f"분류근거: {entry.get('classify_reason') or '-'} · ID #{entry.get('id', '')}"},
            }
        ],
    }


def add_share_reply(
    r,
    team_id: int,
    share_id: int,
    author: str,
    content: str,
    source: str = "web",
    discord_message_id: str = "",
    notify_discord: bool = True,
) -> dict[str, Any]:
    key = f"fw:shares:{team_id}"
    raw_list = r.lrange(key, 0, SHARE_LIMIT - 1)
    target_idx = -1
    target_entry = None
    for idx, raw in enumerate(raw_list):
        try:
            item = json.loads(raw)
            if int(item.get("id") or 0) == share_id:
                target_idx = idx
                target_entry = item
                break
        except Exception:
            continue
    if not target_entry or target_idx < 0:
        return {"ok": False, "error": "not_found"}

    replies = target_entry.get("replies") or []
    ts = int(time.time())
    rep_obj = {
        "id": f"srep-{int(time.time()*1000)}-{len(replies)+1}",
        "author": author,
        "content": content,
        "ts": ts,
        "source": source,
        "discord_message_id": discord_message_id,
    }
    replies.append(rep_obj)
    target_entry["replies"] = replies
    target_entry["updated_at"] = ts
    r.lset(key, target_idx, json.dumps(target_entry, ensure_ascii=False))

    discord_res = {"sent": False, "reason": "skipped"}
    if notify_discord and source == "web":
        msg_payload = {
            "embeds": [
                {
                    "title": f"💬 [공유: {target_entry.get('title') or ''}]에 답변이 등록되었습니다",
                    "description": content,
                    "color": 0x38BDF8,
                    "fields": [
                        {"name": "작성자", "value": author, "inline": True},
                        {"name": "공유 ID", "value": f"#{share_id}", "inline": True},
                    ],
                    "footer": {"text": f"FIGTEAM 협업 허브 · source={source}"},
                }
            ]
        }
        discord_res = send_discord_webhook(msg_payload)
    return {"ok": True, "reply": rep_obj, "share": target_entry, "discord": discord_res}


def add_discord_inbox_reply(
    r,
    team_id: int,
    item_id: int,
    author: str,
    content: str,
    source: str = "web",
    discord_message_id: str = "",
    notify_discord: bool = True,
) -> dict[str, Any]:
    inbox_key = f"fw:discord:inbox:{team_id}"
    raw = r.hget(inbox_key, str(item_id))
    if not raw:
        return {"ok": False, "error": "not_found"}
    entry = json.loads(raw)
    replies = entry.get("replies") or []
    ts = int(time.time())
    rep_obj = {
        "id": f"rep-{int(time.time()*1000)}-{len(replies)+1}",
        "author": author,
        "content": content,
        "ts": ts,
        "source": source,
        "discord_message_id": discord_message_id,
    }
    replies.append(rep_obj)
    entry["replies"] = replies
    entry["updated_at"] = ts
    r.hset(inbox_key, str(item_id), json.dumps(entry, ensure_ascii=False))

    discord_res = {"sent": False, "reason": "skipped"}
    if notify_discord and source == "web":
        msg_payload = {
            "embeds": [
                {
                    "title": f"💬 [{entry.get('title') or '과제/공유'}]에 답변이 등록되었습니다",
                    "description": content,
                    "color": 0x38BDF8,
                    "fields": [
                        {"name": "작성자", "value": author, "inline": True},
                        {"name": "대상 항목", "value": f"#{item_id} {entry.get('category_label') or ''}", "inline": True},
                    ],
                    "footer": {"text": f"FIGTEAM 협업 허브 · source={source}"},
                }
            ]
        }
        discord_res = send_discord_webhook(msg_payload)
    return {"ok": True, "reply": rep_obj, "item": entry, "discord": discord_res}


def ingest_discord_message(
    r,
    team_id: int,
    data: dict[str, Any],
    default_author: str = "Discord",
    notify_discord: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    raw_text = _clean_text(data.get("content") or data.get("text") or data.get("summary"), "content", 2000, required=True)
    reply_to_msg_id = str(data.get("reply_to_msg_id") or data.get("parent_message_id") or (data.get("message_reference") or {}).get("message_id") or "").strip()
    is_reply = bool(reply_to_msg_id)

    if not force and not is_reply and not has_figteam_trigger(raw_text):
        return {"ok": True, "ignored": True, "reason": "no_trigger"}

    ext_msg_id = str(data.get("discord_message_id") or data.get("message_id") or "").strip()[:64]
    seen_key = f"fw:discord:seen:{team_id}"
    if ext_msg_id:
        if r.sismember(seen_key, ext_msg_id):
            return {"ok": True, "duplicate": True, "discord_message_id": ext_msg_id}
        r.sadd(seen_key, ext_msg_id)

    author = _clean_text(data.get("author") or default_author, "author", 40, required=False, default=default_author)
    channel = _clean_text(data.get("channel") or "discord", "channel", 60, required=False, default="discord")

    # 디스코드 봇 메시지에 대한 '답장(Reply)'인 경우 부모 항목(공유 또는 수신과제)을 찾아 댓글로 추가
    if is_reply:
        share_map_key = f"fw:share:msg_map:{team_id}"
        parent_share_id = r.hget(share_map_key, reply_to_msg_id)
        if parent_share_id:
            rep_res = add_share_reply(
                r,
                team_id=team_id,
                share_id=int(parent_share_id),
                author=author,
                content=raw_text,
                source="discord",
                discord_message_id=ext_msg_id,
                notify_discord=False,
            )
            if rep_res.get("ok"):
                return {"ok": True, "reply": True, "parent_share_id": int(parent_share_id), "share": rep_res["share"]}

        msg_map_key = f"fw:discord:msg_map:{team_id}"
        parent_item_id = r.hget(msg_map_key, reply_to_msg_id)
        if parent_item_id:
            rep_res = add_discord_inbox_reply(
                r,
                team_id=team_id,
                item_id=int(parent_item_id),
                author=author,
                content=raw_text,
                source="discord",
                discord_message_id=ext_msg_id,
                notify_discord=False,
            )
            if rep_res.get("ok"):
                return {"ok": True, "reply": True, "parent_item_id": int(parent_item_id), "item": rep_res["item"]}

    cat_override = str(data.get("category") or "").strip().lower()
    cls = classify_discord_message(raw_text, category_override=cat_override)
    area = _clean_text(data.get("area"), "area", 60, required=False, default=cls["area"]) or cls["area"]
    category = cls["category"]
    task_status = "open" if category == "task" else "read"

    item_id = int(r.incr("fw:seq:discord_inbox"))
    ts = int(data.get("ts") or time.time())
    entry: dict[str, Any] = {
        "id": item_id,
        "ts": ts,
        "updated_at": ts,
        "discord_message_id": ext_msg_id,
        "reply_to_msg_id": reply_to_msg_id,
        "channel": channel,
        "author": author,
        "raw_text": raw_text,
        "title": cls["title"],
        "summary": cls["clean_text"],
        "category": category,
        "category_label": cls["category_label"],
        "task_status": task_status,
        "task_status_label": DISCORD_TASK_STATUS_META.get(task_status, task_status),
        "classify_reason": cls["reason"],
        "hashtags": cls["hashtags"],
        "mentions": cls["mentions"],
        "area": area,
        "crosscheck_hints": cls["crosscheck_hints"],
        "source": str(data.get("source") or "discord")[:32],
        "linked_goal_id": None,
        "handled_by": "",
        "replies": [],
    }

    inbox_key = f"fw:discord:inbox:{team_id}"
    order_key = f"fw:discord:order:{team_id}"
    msg_map_key = f"fw:discord:msg_map:{team_id}"
    p = r.pipeline()
    p.hset(inbox_key, str(item_id), json.dumps(entry, ensure_ascii=False))
    p.lpush(order_key, str(item_id))
    p.ltrim(order_key, 0, DISCORD_INBOX_LIMIT - 1)
    if ext_msg_id:
        p.hset(msg_map_key, ext_msg_id, str(item_id))
    p.execute()

    discord_res: dict[str, Any] = {"sent": False, "reason": "skipped"}
    if notify_discord:
        discord_res = send_discord_webhook(format_discord_inbound_embed(entry, event_label="접수"))
    return {"ok": True, "item": entry, "discord": discord_res}


def list_discord_inbox(r, team_id: int, category: str = "all", limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), DISCORD_INBOX_LIMIT))
    inbox_key = f"fw:discord:inbox:{team_id}"
    order_key = f"fw:discord:order:{team_id}"
    ids = [x for x in r.lrange(order_key, 0, DISCORD_INBOX_LIMIT - 1)]
    if not ids:
        raw_map = r.hgetall(inbox_key)
        ids = sorted(raw_map.keys(), key=lambda x: int(x) if str(x).isdigit() else 0, reverse=True)
    cat_q = str(category or "all").strip().lower()
    out: list[dict[str, Any]] = []
    for iid in ids:
        raw = r.hget(inbox_key, str(iid))
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if cat_q == "task" and item.get("category") != "task":
            continue
        if cat_q == "open_task" and not (item.get("category") == "task" and item.get("task_status") != "done"):
            continue
        if cat_q == "share" and item.get("category") != "share":
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def summarize_discord_inbox(items: list[dict[str, Any]]) -> dict[str, int]:
    total = len(items)
    tasks_open = 0
    tasks_in_progress = 0
    tasks_done = 0
    shares = 0
    for it in items:
        if it.get("category") == "task":
            st = it.get("task_status") or "open"
            if st == "done":
                tasks_done += 1
            elif st == "in_progress":
                tasks_in_progress += 1
            else:
                tasks_open += 1
        else:
            shares += 1
    return {
        "total": total,
        "tasks_open": tasks_open,
        "tasks_in_progress": tasks_in_progress,
        "tasks_done": tasks_done,
        "tasks_total": tasks_open + tasks_in_progress + tasks_done,
        "shares": shares,
    }


def update_discord_inbox_item(
    r,
    s: auth.Session,
    item_id: int,
    data: dict[str, Any],
    send_discord: bool = True,
) -> dict[str, Any]:
    inbox_key = f"fw:discord:inbox:{s.team_id}"
    raw = r.hget(inbox_key, str(item_id))
    if not raw:
        raise ApiError(404, f"Discord 메시지 #{item_id} 를 찾을 수 없습니다")
    item = json.loads(raw)

    prev_cat = item.get("category") or "share"
    prev_st = item.get("task_status") or "open"
    new_cat = str(data.get("category") or prev_cat).strip().lower()
    if new_cat not in DISCORD_CATEGORY_META:
        new_cat = prev_cat
    item["category"] = new_cat
    item["category_label"] = DISCORD_CATEGORY_META[new_cat][0]

    req_st = str(data.get("task_status") or "").strip().lower()
    if req_st in DISCORD_TASK_STATUS_META:
        item["task_status"] = req_st
    elif new_cat != prev_cat:
        item["task_status"] = "open" if new_cat == "task" else "read"
    item["task_status_label"] = DISCORD_TASK_STATUS_META.get(item["task_status"], item["task_status"])
    item["handled_by"] = f"{s.member} ({s.access_key})" if s.access_key else s.member
    item["updated_at"] = int(time.time())

    goal_created: dict[str, Any] | None = None
    if data.get("promote_goal"):
        item["category"] = "task"
        item["category_label"] = DISCORD_CATEGORY_META["task"][0]
        if item["task_status"] not in ("in_progress", "done"):
            item["task_status"] = "open"
            item["task_status_label"] = DISCORD_TASK_STATUS_META["open"]
        g_res = upsert_goal(
            r,
            s,
            {
                "title": f"[Discord] {item.get('title') or '과제'}",
                "area": item.get("area") or "figteaminfra",
                "owner": s.member,
                "status": "in_progress" if item["task_status"] == "in_progress" else "todo",
                "note": (item.get("summary") or "")[:400],
            },
            send_discord=False,
        )
        goal_created = g_res["goal"]
        item["linked_goal_id"] = goal_created["id"]

    r.hset(inbox_key, str(item_id), json.dumps(item, ensure_ascii=False))
    if s.access_key:
        auth.record_access(
            r,
            s.team_id,
            s.member,
            s.access_key,
            "discord",
            detail=f"#{item_id} [{item['category_label']}/{item['task_status_label']}]",
        )

    discord_res: dict[str, Any] = {"sent": False, "reason": "skipped"}
    if send_discord and (item["task_status"] != prev_st or item["category"] != prev_cat or goal_created):
        discord_res = send_discord_webhook(format_discord_inbound_embed(item, event_label="웹 처리"))

    out: dict[str, Any] = {"ok": True, "item": item, "discord": discord_res}
    if goal_created:
        out["goal"] = goal_created
    return out


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
        "replies": [],
    }

    discord_res: dict[str, Any] = {"sent": False, "reason": "skipped"}
    if send_discord:
        discord_res = send_discord_webhook(format_share_embed(entry, hints))
        entry["discord_sent"] = bool(discord_res.get("sent"))
        d_msg_id = str(discord_res.get("message_id") or "").strip()
        if d_msg_id:
            entry["discord_message_id"] = d_msg_id
            r.hset(f"fw:share:msg_map:{s.team_id}", d_msg_id, str(share_id))

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
            '<div><label>접속 키값</label><input type="text" value="서버 자동 할당 (변경 불가)" readonly style="color:#93c5fd;"></div>'
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
    discord_items: list[dict[str, Any]] | None = None,
    recent_changes: list[dict[str, Any]] | None = None,
) -> str:
    esc = html.escape
    goals_list = goals or []
    gs = summarize_goals(goals_list)
    err_html = f'<div class="alert alert-err">{esc(error)}</div>' if error else ""
    notice_html = f'<div class="alert alert-ok">{esc(notice)}</div>' if notice else ""
    dc_status_label = "Discord 연동됨" if discord_configured else "Discord 미연동"
    dc_status_class = "ok" if discord_configured else "warn"

    member_name = esc(session.member) if session else ""
    access_key = esc(session.access_key) if (session and session.access_key) else ""
    is_logged_in = bool(session)

    if session:
        user_header_html = (
            f'<div class="g-user-badge">'
            f'<span class="g-user-dot"></span>'
            f'<span class="g-user-name">{member_name}</span>'
            f'<span class="g-user-key">{access_key}</span>'
            f'</div>'
        )
    else:
        user_header_html = (
            '<div class="g-user-badge guest" id="g-login-status">'
            '<span class="g-user-dot warn"></span>'
            '<span class="g-user-name">포털 사용자 확인 중...</span>'
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
        note_html = f'<div class="card-desc" style="margin-top:6px;">{esc(g_item["note"])}</div>' if g_item.get("note") else ""
        st_btns: list[str] = []
        if session:
            for k_btn, (lbl_btn, _) in GOAL_STATUS_META.items():
                active_cls = " act-btn active" if k_btn == st_k else " act-btn"
                st_btns.append(
                    f'<form method="post" action="/api/ai/hub/goal-status" style="display:inline;">'
                    f'<input type="hidden" name="goal_id" value="{g_item["id"]}">'
                    f'<input type="hidden" name="status" value="{esc(k_btn)}">'
                    f'<button type="submit" class="{active_cls}">{esc(lbl_btn)}</button>'
                    f'</form>'
                )
        goal_cards.append(
            '<div class="work-card">'
            f'<div class="card-head">'
            f'<div><span class="tag tag-target">목표 #{g_item["id"]}</span> <span class="tag tag-status">{esc(st_lbl)}</span> <span class="tag tag-area">{esc(g_item.get("area") or "general")}</span></div>'
            f'<div class="card-meta">담당자: {esc(g_item.get("owner") or "미지정")}{due}</div>'
            f'</div>'
            f'<div class="card-title">{esc(g_item.get("title") or "")}</div>'
            f'{note_html}'
            f'<div class="card-actions" style="margin-top:10px;">{"".join(st_btns)}</div>'
            '</div>'
        )
    goals_board_html = "".join(goal_cards) if goal_cards else '<div class="empty-box">등록된 팀 목표가 없습니다. 아래에서 첫 목표를 등록하세요.</div>'

    cur_status = prefill.get("status") or "info"
    opts = []
    for k, (label, _) in STATUS_META.items():
        sel = " selected" if k == cur_status else ""
        opts.append(f'<option value="{esc(k)}"{sel}>{esc(label)}</option>')
    options_html = "".join(opts)

    cur_goal_st = prefill.get("goal_status") or ""
    g_st_opts = ['<option value="">연계 목표 상태 유지</option>']
    for k, (label, _) in GOAL_STATUS_META.items():
        sel = " selected" if k == cur_goal_st else ""
        g_st_opts.append(f'<option value="{esc(k)}"{sel}>연계 목표를 [{esc(label)}] 상태로 변경</option>')

    feed_rows: list[str] = []
    for item in shares[:20]:
        ak_txt = f" ({esc(item['access_key'])})" if item.get("access_key") else ""
        dc_txt = " · Discord 발송됨" if item.get("discord_sent") else ""
        g_badge = f' <span class="tag tag-target">목표 #{item["goal_id"]}</span>' if item.get("goal_id") else ""
        chk = (
            f'<div class="card-alert" style="margin-top:8px;">확인 요청: {esc(item["check_request"])}</div>'
            if item.get("check_request")
            else ""
        )
        url_link = (
            f'<div style="margin-top:6px;font-size:12px;"><a href="{esc(item["cfg_url"])}" target="_blank" rel="noopener" class="link-btn">관련 #cfg 설정 열기 ↗</a></div>'
            if item.get("cfg_url")
            else ""
        )
        # 답변 / 댓글 스레드 렌더링
        replies = item.get("replies") or []
        rep_html_list = []
        for rep in replies:
            src_lbl = "디스코드" if rep.get("source") == "discord" else "웹"
            src_tag = f'<span class="reply-src-badge">{src_lbl}</span>'
            rep_html_list.append(
                f'<div class="reply-item">'
                f'<div class="reply-meta"><b>{esc(rep.get("author") or "작성자")}</b> {src_tag} · {_fmt_ts(rep.get("ts", 0))}</div>'
                f'<div class="reply-content">{esc(rep.get("content") or "")}</div>'
                f'</div>'
            )
        replies_block = ""
        if rep_html_list:
            replies_block = (
                f'<div class="card-replies-box">'
                f'<div class="reply-header">답변 및 조치 내역 ({len(replies)}건)</div>'
                f'{"".join(rep_html_list)}'
                f'</div>'
            )

        reply_form_html = ""
        if session:
            reply_form_html = (
                f'<form method="post" action="/api/ai/hub/reply" class="inline-reply-form" style="margin-top:10px;">'
                f'<input type="hidden" name="share_id" value="{item["id"]}">'
                f'<input type="hidden" name="tab" value="dispatch">'
                f'<div style="display:flex;gap:6px;">'
                f'<input type="text" name="content" placeholder="답변이나 조치 경과를 입력하세요..." required style="flex:1;padding:6px 10px;font-size:12px;">'
                f'<button type="submit" class="act-btn" style="padding:6px 12px;font-size:12px;white-space:nowrap;">답변 등록</button>'
                f'</div></form>'
            )

        feed_rows.append(
            '<div class="work-card border-share">'
            f'<div class="card-head">'
            f'<div><span class="tag tag-share">{esc(item.get("status_label") or "공유")}</span> <span class="tag tag-area">{esc(item.get("area") or "general")}</span>{g_badge}</div>'
            f'<div class="card-meta">{esc(item.get("author") or "게스트")}{ak_txt} · {_fmt_ts(item.get("ts", 0))}{dc_txt}</div>'
            f'</div>'
            f'<div class="card-title">{esc(item.get("title") or "")}</div>'
            f'<div class="card-desc">{esc(item.get("summary") or "")}</div>'
            f'{chk}{url_link}'
            f'{replies_block}'
            f'{reply_form_html}</div>'
        )
    feed_html = "".join(feed_rows) if feed_rows else '<div class="empty-box">등록된 팀 공유 내역이 없습니다.</div>'

    dc_list = discord_items or []
    dc_sum = summarize_discord_inbox(dc_list)
    dc_filter = str(prefill.get("dc_filter") or "all").strip().lower()
    dc_cards: list[str] = []
    for d_it in dc_list[:30]:
        d_cat = d_it.get("category") or "share"
        if dc_filter == "task" and d_cat != "task":
            continue
        if dc_filter == "open_task" and not (d_cat == "task" and d_it.get("task_status") != "done"):
            continue
        if dc_filter == "share" and d_cat != "share":
            continue
        d_st = d_it.get("task_status") or ("open" if d_cat == "task" else "read")
        cat_lbl = "과제" if d_cat == "task" else "공유"
        st_lbl = d_it.get("task_status_label") or DISCORD_TASK_STATUS_META.get(d_st, d_st)
        goal_chip = f' <span class="tag tag-target">목표 #{d_it["linked_goal_id"]}</span>' if d_it.get("linked_goal_id") else ""
        dc_acts = ""
        if session:
            next_cat = "share" if d_cat == "task" else "task"
            next_cat_lbl = "공유로 전환" if d_cat == "task" else "과제로 전환"
            dc_acts = '<div class="card-actions" style="margin-top:10px;">'
            if d_cat == "task":
                dc_acts += (
                    f'<form method="post" action="/api/ai/hub/discord-state" style="display:inline;">'
                    f'<input type="hidden" name="item_id" value="{d_it["id"]}"><input type="hidden" name="task_status" value="in_progress">'
                    f'<button type="submit" class="act-btn">진행 시작</button></form>'
                    f'<form method="post" action="/api/ai/hub/discord-state" style="display:inline;">'
                    f'<input type="hidden" name="item_id" value="{d_it["id"]}"><input type="hidden" name="task_status" value="done">'
                    f'<button type="submit" class="act-btn btn-done">완료</button></form>'
                )
                if not d_it.get("linked_goal_id"):
                    dc_acts += (
                        f'<form method="post" action="/api/ai/hub/discord-state" style="display:inline;">'
                        f'<input type="hidden" name="item_id" value="{d_it["id"]}"><input type="hidden" name="promote_goal" value="1">'
                        f'<button type="submit" class="act-btn">공동목표 승격</button></form>'
                    )
            else:
                dc_acts += (
                    f'<form method="post" action="/api/ai/hub/discord-state" style="display:inline;">'
                    f'<input type="hidden" name="item_id" value="{d_it["id"]}"><input type="hidden" name="task_status" value="read">'
                    f'<button type="submit" class="act-btn">확인 완료</button></form>'
                )
            dc_acts += (
                f'<form method="post" action="/api/ai/hub/discord-state" style="display:inline;">'
                f'<input type="hidden" name="item_id" value="{d_it["id"]}"><input type="hidden" name="category" value="{next_cat}">'
                f'<button type="submit" class="act-btn">{next_cat_lbl}</button></form></div>'
            )
        tag_cls = "tag-task" if d_cat == "task" else "tag-share"
        card_border = "border-task" if d_cat == "task" else "border-share"

        replies = d_it.get("replies") or []
        rep_html_list = []
        for rep in replies:
            src_lbl = "디스코드" if rep.get("source") == "discord" else "웹"
            src_tag = f'<span class="reply-src-badge">{src_lbl}</span>'
            rep_html_list.append(
                f'<div class="reply-item">'
                f'<div class="reply-meta"><b>{esc(rep.get("author") or "작성자")}</b> {src_tag} · {_fmt_ts(rep.get("ts", 0))}</div>'
                f'<div class="reply-content">{esc(rep.get("content") or "")}</div>'
                f'</div>'
            )
        replies_block = ""
        if rep_html_list:
            replies_block = (
                f'<div class="card-replies-box">'
                f'<div class="reply-header">답변 및 조치 내역 ({len(replies)}건)</div>'
                f'{"".join(rep_html_list)}'
                f'</div>'
            )

        reply_form_html = ""
        if session:
            reply_form_html = (
                f'<form method="post" action="/api/ai/hub/reply" class="inline-reply-form" style="margin-top:10px;">'
                f'<input type="hidden" name="item_id" value="{d_it["id"]}">'
                f'<input type="hidden" name="tab" value="inbox">'
                f'<div style="display:flex;gap:6px;">'
                f'<input type="text" name="content" placeholder="답변이나 조치 경과를 입력하세요..." required style="flex:1;padding:6px 10px;font-size:12px;">'
                f'<button type="submit" class="act-btn" style="padding:6px 12px;font-size:12px;white-space:nowrap;">답변 등록</button>'
                f'</div></form>'
            )

        dc_cards.append(
            f'<div class="work-card {card_border}">'
            f'<div class="card-head">'
            f'<div><span class="tag {tag_cls}">{esc(cat_lbl)}</span> <span class="tag tag-status">{esc(st_lbl)}</span> <span class="tag tag-area">{esc(d_it.get("area") or "figteaminfra")}</span>{goal_chip}</div>'
            f'<div class="card-meta">{esc(d_it.get("author") or "Discord")} · #{esc(d_it.get("channel") or "figteam")} · {_fmt_ts(d_it.get("ts", 0))}</div>'
            f'</div>'
            f'<div class="card-title">{esc(d_it.get("title") or "")}</div>'
            f'<div class="card-desc">{esc(d_it.get("summary") or d_it.get("raw_text") or "")}</div>'
            f'<div class="card-sub-info">분류 근거: {esc(d_it.get("classify_reason") or "키워드")}</div>'
            f'{replies_block}'
            f'{dc_acts}'
            f'{reply_form_html}</div>'
        )
    discord_inbox_html = "".join(dc_cards) if dc_cards else '<div class="empty-box">접수된 Discord 과제 또는 공유 메시지가 없습니다.</div>'

    ch_list = recent_changes or []
    ch_rows = "".join(
        f'<div class="work-card">'
        f'<div class="card-head">'
        f'<div><span class="tag tag-area">{esc(c.get("kind") or "문서")}</span> <b>{esc(c.get("title") or "(제목 없음)")}</b> (r{c.get("rev", 1)})</div>'
        f'<div class="card-meta">{esc(c.get("matched_user") or c.get("author") or "-")} · {_fmt_ts(c.get("created_at", 0))}</div>'
        f'</div>'
        f'<div class="card-desc">{esc(c.get("message") or "문서 업데이트")}</div>'
        f'<div style="margin-top:6px;"><a href="/#cfg/" target="_blank" rel="noopener" class="link-btn">설계/설정(#cfg) 포털에서 확인 ↗</a></div>'
        f'</div>'
        for c in ch_list[:12]
    )
    recent_changes_html = ch_rows if ch_rows else '<div class="empty-box">최근 문서 변경 이력이 없습니다.</div>'

    full_prompt_txt = esc(ai_prompts[0] or "")
    default_tab = str(prefill.get("tab") or "inbox").strip().lower()
    if default_tab not in ("inbox", "dispatch", "goals", "portal"):
        default_tab = "inbox"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>FIGTEAM 인프라 협업 허브</title>
  <style>
    /* CSS 변수: 메인 포털과 100% 동일한 디자인 시스템 */
    :root {{
      --bg: #0b1120;
      --surface: #0f172a;
      --surface-border: #1e293b;
      --text-main: #f8fafc;
      --text-sub: #94a3b8;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --blue: #38bdf8;
      --green: #10b981;
      --yellow: #f59e0b;
      --border-color: #334155;
      --font-mono: 'JetBrains Mono', 'Pretendard', monospace;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background-color: var(--bg);
      color: var(--text-main);
      font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    a {{ color: #60a5fa; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}

    /* 1. TOP HEADER (메인 포털 https://figteam.ktci5.kr/ 와 100% 동일한 FHD FIXED 레이아웃) */
    header {{
      height: 52px;
      border-bottom: 1px solid var(--surface-border);
      background: rgba(15, 23, 42, 0.96);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      flex-shrink: 0;
      gap: 12px;
      position: sticky;
      top: 0;
      z-index: 100;
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-shrink: 0;
    }}
    .brand-title {{
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }}
    .brand-tag {{
      font-size: 10.5px;
      font-weight: 600;
      background: #1e293b;
      color: var(--blue);
      border: 1px solid #0284c7;
      padding: 1px 6px;
      border-radius: 4px;
      font-family: var(--font-mono);
    }}
    .header-clock-timer {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 11.5px;
      font-family: var(--font-mono);
      color: var(--text-sub);
      background: #090d16;
      border: 1px solid var(--surface-border);
      padding: 3px 10px;
      border-radius: 4px;
      white-space: nowrap;
    }}
    .pulse-dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--blue);
      box-shadow: 0 0 6px var(--blue);
    }}

    /* TOP INFRASTATUS INDIVIDUAL BADGES */
    .header-infra-status {{
      display: flex;
      align-items: center;
      gap: 6px;
      overflow-x: auto;
      flex: 1;
      justify-content: center;
    }}
    .infra-badge-item {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: #141e33;
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 2px 7px;
      font-size: 11px;
      white-space: nowrap;
    }}
    .infra-badge-name {{
      font-weight: 600;
      color: #cbd5e1;
    }}
    .infra-badge-state {{
      font-family: var(--font-mono);
      font-size: 10.5px;
      font-weight: 700;
      padding: 1px 4px;
      border-radius: 3px;
    }}
    .state-green {{
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
    }}
    .state-amber {{
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
    }}

    /* HEADER RIGHT NAV BUTTONS */
    .header-right {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }}
    .fs-ctl {{ display: inline-flex; gap: 2px; margin-right: 6px; border: 1px solid var(--surface-border); border-radius: 5px; overflow: hidden; }}
    .fs-btn {{ background: transparent; border: 0; color: var(--text-sub); padding: 4px 8px; font-size: 12px; cursor: pointer; font-family: inherit; }}
    .fs-btn:hover {{ background: #1f2937; color: #fff; }}
    .fs-btn + .fs-btn {{ border-left: 1px solid var(--surface-border); }}
    .nav-btn {{
      background: #1e293b;
      border: 1px solid var(--surface-border);
      color: var(--text-sub);
      padding: 5px 12px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
    }}
    .nav-btn:hover {{
      background: #334155;
      color: #fff;
      text-decoration: none;
    }}
    .nav-btn.active {{
      background: var(--primary);
      color: #fff;
      border-color: #3b82f6;
    }}
    .logout-btn {{
      background: transparent;
      border: 1px solid var(--surface-border);
      color: var(--text-sub);
      padding: 5px 10px;
      border-radius: 4px;
      font-size: 11.5px;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
      display: inline-flex;
      align-items: center;
      text-decoration: none;
    }}
    .logout-btn:hover {{
      background: #1f2937;
      color: #fff;
      border-color: #4b5563;
    }}
    .g-user-badge {{
      display: flex;
      align-items: center;
      gap: 6px;
      background: #090d16;
      border: 1px solid var(--surface-border);
      border-radius: 4px;
      padding: 4px 10px;
      font-size: 11.5px;
    }}
    .g-user-dot {{ width: 6px; height: 6px; border-radius: 50%; background: #10b981; box-shadow: 0 0 6px #10b981; }}
    .g-user-dot.warn {{ background: #f59e0b; box-shadow: none; }}
    .g-user-name {{ font-weight: 700; color: #f8fafc; }}
    .g-user-key {{ font-family: var(--font-mono); color: #93c5fd; font-size: 11px; }}

    /* 2. 메인 워크스페이스 레이아웃 (이메일 클라이언트 형태의 계단식 사이드바) */
    .hub-container {{
      display: grid;
      grid-template-columns: 240px 1fr;
      flex: 1;
      min-height: calc(100vh - 52px);
    }}
    @media (max-width: 900px) {{
      .hub-container {{ grid-template-columns: 1fr; }}
    }}

    /* 좌측 사이드바: 이메일 클라이언트형 계단식(Tree) 네비게이션 */
    .hub-side {{
      background: #090e1a;
      border-right: 1px solid var(--surface-border);
      padding: 14px 10px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      overflow-y: auto;
    }}

    /* 계단식 트리 그룹 */
    .tree-group {{
      display: flex;
      flex-direction: column;
      margin-bottom: 4px;
    }}
    .tree-root {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 8px;
      border-radius: 5px;
      font-size: 11.5px;
      font-weight: 800;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: .04em;
      cursor: pointer;
      user-select: none;
      transition: all .12s;
    }}
    .tree-root:hover {{
      background: rgba(255, 255, 255, .04);
      color: #f1f5f9;
    }}
    .tree-root-left {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .tree-arrow {{
      font-size: 9px;
      display: inline-block;
      transition: transform .15s ease;
      color: #64748b;
    }}
    .tree-group.collapsed .tree-arrow {{
      transform: rotate(-90deg);
    }}
    .tree-group.collapsed .tree-children {{
      display: none;
    }}

    /* 계단식 하위 트리 컨테이너 (수직 가이드선 포함) */
    .tree-children {{
      display: flex;
      flex-direction: column;
      margin-left: 10px;
      padding-left: 8px;
      border-left: 1px solid #1e293b;
      gap: 2px;
      margin-top: 2px;
    }}

    /* 1차 하위: 수신함, 발신함 */
    .tree-node {{
      display: flex;
      flex-direction: column;
      margin-bottom: 2px;
    }}
    .tree-node-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 8px;
      border-radius: 5px;
      font-size: 12.5px;
      font-weight: 700;
      color: #cbd5e1;
      cursor: pointer;
      transition: all .12s;
      background: transparent;
      border: 1px solid transparent;
      width: 100%;
      text-align: left;
    }}
    .tree-node-head:hover {{
      background: #1e293b;
      color: #fff;
    }}
    .tree-node-head.active {{
      background: rgba(37, 99, 235, .15);
      color: #60a5fa;
      border-color: rgba(59, 130, 246, .3);
    }}

    /* 2차 하위: 과제 목록, 신규 접수 등 (계단식 2단계 들여쓰기) */
    .tree-sub-children {{
      display: flex;
      flex-direction: column;
      margin-left: 8px;
      padding-left: 8px;
      border-left: 1px dotted #25334d;
      gap: 2px;
      margin-top: 1px;
      margin-bottom: 4px;
    }}
    .tree-leaf {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      border-radius: 4px;
      font-size: 12px;
      font-weight: 600;
      color: #94a3b8;
      cursor: pointer;
      background: transparent;
      border: 0;
      text-align: left;
      width: 100%;
      transition: all .12s;
    }}
    .tree-leaf:hover {{
      background: #1e293b;
      color: #fff;
    }}
    .tree-leaf.active {{
      background: #1e40af;
      color: #fff;
      font-weight: 700;
    }}
    .badge-count {{
      font-size: 11px;
      font-weight: 800;
      padding: 1px 6px;
      border-radius: 999px;
      background: #0f172a;
      color: #94a3b8;
    }}
    .badge-warn {{ background: rgba(245,158,11,.2); color: #fde68a !important; }}

    /* 3. 우측 바디 콘텐츠 */
    .hub-content {{
      padding: 20px 28px;
      max-width: 1120px;
      overflow-y: auto;
    }}
    @media (max-width: 900px) {{
      .hub-content {{ padding: 14px 12px; }}
    }}

    /* 바디 상단 작업 메뉴 (바디에 나눠진 작업을 메뉴로 분리) */
    .task-nav-bar {{
      display: flex;
      gap: 4px;
      background: #090e1a;
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 4px;
      margin-bottom: 18px;
      width: fit-content;
    }}
    .task-tab-btn {{
      background: transparent;
      border: 0;
      color: #94a3b8;
      padding: 6px 14px;
      border-radius: 4px;
      font-size: 12.5px;
      font-weight: 700;
      cursor: pointer;
      transition: all .15s;
    }}
    .task-tab-btn:hover {{
      color: #fff;
      background: #1e293b;
    }}
    .task-tab-btn.active {{
      background: #2563eb;
      color: #fff;
    }}

    /* 작업 뷰 영역 */
    .task-view {{ display: none; }}
    .task-view.active {{ display: block; animation: fadeIn .12s ease-in-out; }}

    /* 섹션 패널 */
    .pane {{ display: none; }}
    .pane.active {{ display: block; animation: fadeIn .12s ease-in-out; }}
    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(2px); }} to {{ opacity: 1; transform: translateY(0); }} }}

    .pane-header {{ margin-bottom: 16px; }}
    .pane-title {{ font-size: 19px; font-weight: 800; color: #fff; margin: 0 0 4px; }}
    .pane-desc {{ font-size: 12.5px; color: #94a3b8; margin: 0; line-height: 1.5; }}

    /* 카드 */
    .work-card {{
      background: #0f172a;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 14px 16px;
      margin-bottom: 10px;
      transition: border-color .15s;
    }}
    .work-card:hover {{ border-color: #334155; }}
    .border-task {{ border-left: 4px solid #f59e0b; }}
    .border-share {{ border-left: 4px solid #38bdf8; }}

    .card-head {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }}
    .card-title {{ font-size: 14.5px; font-weight: 800; color: #fff; margin-bottom: 6px; }}
    .card-desc {{ font-size: 13px; color: #cbd5e1; white-space: pre-wrap; line-height: 1.55; }}
    .card-meta {{ font-size: 11.5px; color: #94a3b8; }}
    .card-sub-info {{ font-size: 11px; color: #64748b; margin-top: 6px; }}
    .card-alert {{ background: rgba(245,158,11,.12); border: 1px solid rgba(245,158,11,.3); border-radius: 6px; padding: 6px 10px; font-size: 12px; color: #fde68a; }}

    /* 답변 및 댓글 스레드 */
    .card-replies-box {{
      background: #080c16;
      border: 1px solid var(--surface-border);
      border-radius: 6px;
      padding: 10px 12px;
      margin-top: 10px;
    }}
    .reply-header {{
      font-size: 11.5px;
      font-weight: 700;
      color: #94a3b8;
      margin-bottom: 6px;
    }}
    .reply-item {{
      padding: 6px 0;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }}
    .reply-item:first-child {{
      border-top: 0;
      padding-top: 2px;
    }}
    .reply-meta {{
      font-size: 11px;
      color: #64748b;
      margin-bottom: 2px;
    }}
    .reply-meta b {{
      color: #cbd5e1;
    }}
    .reply-src-badge {{
      font-size: 10px;
      font-weight: 700;
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.12);
      padding: 1px 4px;
      border-radius: 3px;
      margin-left: 3px;
    }}
    .reply-content {{
      font-size: 12.5px;
      color: #e2e8f0;
      white-space: pre-wrap;
      line-height: 1.45;
    }}
    .inline-reply-form input {{
      background: #080c16 !important;
    }}

    /* 태그 */
    .tag {{ display: inline-block; font-size: 10.5px; font-weight: 800; padding: 2px 6px; border-radius: 4px; margin-right: 4px; }}
    .tag-task {{ background: rgba(245,158,11,.16); color: #fde68a; border: 1px solid #d97706; }}
    .tag-share {{ background: rgba(56,189,248,.14); color: #7dd3fc; border: 1px solid #0284c7; }}
    .tag-status {{ background: #1e293b; color: #cbd5e1; border: 1px solid #334155; }}
    .tag-area {{ background: #0b1220; color: #93c5fd; border: 1px solid #1e3a8a; font-family: var(--font-mono); }}
    .tag-target {{ background: rgba(16,185,129,.14); color: #6ee7b7; border: 1px solid #059669; }}

    /* 버튼류 */
    .act-btn {{
      padding: 4px 10px;
      border-radius: 5px;
      font-size: 11.5px;
      font-weight: 700;
      cursor: pointer;
      background: #1e293b;
      border: 1px solid #334155;
      color: #cbd5e1;
      transition: all .1s;
    }}
    .act-btn:hover {{ border-color: #60a5fa; color: #fff; }}
    .act-btn.active {{ background: #2563eb; border-color: #3b82f6; color: #fff; }}
    .btn-done {{ background: #059669; border-color: #10b981; color: #fff; }}
    .btn-done:hover {{ background: #047857; }}
    .btn-submit {{
      background: #2563eb;
      color: #fff;
      border: 0;
      border-radius: 6px;
      padding: 9px 18px;
      font-size: 13.5px;
      font-weight: 800;
      cursor: pointer;
      transition: background .15s;
    }}
    .btn-submit:hover {{ background: #1d4ed8; }}
    .card-actions {{ display: flex; gap: 6px; flex-wrap: wrap; }}

    /* 폼 스타일 */
    .form-panel {{
      background: #0f172a;
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 16px;
    }}
    .form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }}
    @media (max-width: 640px) {{ .form-row {{ grid-template-columns: 1fr; }} }}
    .form-group {{ margin-bottom: 12px; }}
    .form-label {{ display: block; font-size: 11.5px; font-weight: 700; color: #94a3b8; margin-bottom: 5px; }}
    input[type=text], input[type=password], select, textarea {{
      width: 100%;
      background: #0b1220;
      border: 1px solid var(--surface-border);
      color: #fff;
      border-radius: 5px;
      padding: 8px 10px;
      font-size: 13px;
      font-family: inherit;
    }}
    input:focus, select:focus, textarea:focus {{ outline: none; border-color: #3b82f6; }}
    textarea {{ min-height: 85px; resize: vertical; line-height: 1.5; }}

    .quick-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 10px; }}
    .chip-btn {{
      padding: 4px 8px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 700;
      cursor: pointer;
      background: #0b1220;
      border: 1px solid var(--surface-border);
      color: #94a3b8;
    }}
    .chip-btn:hover {{ border-color: #3b82f6; color: #fff; background: #1e293b; }}

    /* KPI 바 */
    .kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 14px; }}
    .kpi-box {{ background: #0f172a; border: 1px solid var(--surface-border); border-radius: 6px; padding: 8px 10px; }}
    .kpi-title {{ font-size: 11px; color: #94a3b8; font-weight: 700; margin-bottom: 3px; }}
    .kpi-val {{ font-size: 16px; font-weight: 900; color: #fff; }}

    .filter-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }}
    .filter-pill {{
      padding: 5px 11px;
      border-radius: 5px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      background: #0f172a;
      border: 1px solid var(--surface-border);
      color: #94a3b8;
      text-decoration: none;
    }}
    .filter-pill:hover {{ color: #fff; border-color: #334155; text-decoration: none; }}
    .filter-pill.active {{ background: #1e40af; border-color: #3b82f6; color: #fff; text-decoration: none; }}

    /* 알림 박스 */
    .alert {{ padding: 10px 14px; border-radius: 6px; font-size: 12.5px; margin-bottom: 14px; }}
    .alert-ok {{ background: rgba(16,185,129,.14); border: 1px solid rgba(16,185,129,.35); color: #a7f3d0; }}
    .alert-err {{ background: rgba(239,68,68,.14); border: 1px solid rgba(239,68,68,.35); color: #fecaca; }}
    .empty-box {{ text-align: center; padding: 28px 16px; color: #64748b; font-size: 13px; background: #0f172a; border: 1px dashed var(--surface-border); border-radius: 6px; }}

    .prog-bar {{ height: 8px; background: #0b1220; border-radius: 999px; overflow: hidden; margin: 8px 0 14px; border: 1px solid var(--surface-border); }}
    .prog-fill {{ height: 100%; background: #10b981; }}
  </style>
</head>
<body>
  <!-- 1. TOP HEADER (포털과 100% 동일한 FHD FIXED 메인 헤더 레이아웃) -->
  <header>
    <div class="header-left">
      <div class="brand-title">
        <a href="/" style="color:#fff;text-decoration:none;display:flex;align-items:center;gap:6px;">
          <span>FIGTEAM 하이브리드 멀티클라우드</span>
          <span class="brand-tag">v2.0 FHD</span>
        </a>
      </div>
      <div class="header-clock-timer">
        <span id="current-clock">2026-11-28 00:00:00 KST</span>
        <span>·</span>
        <div class="pulse-dot"></div>
        <span id="timer-label">인프라 텔레메트리 연동</span>
      </div>
    </div>

    <!-- INDIVIDUAL INFRASTRUCTURE STATUS BADGES -->
    <div class="header-infra-status">
      <div class="infra-badge-item">
        <span class="infra-badge-name">KT Edge</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <div class="infra-badge-item">
        <span class="infra-badge-name">온프렘 cp1</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <div class="infra-badge-item">
        <span class="infra-badge-name">온프렘 db01</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <div class="infra-badge-item">
        <span class="infra-badge-name">AWS CTL</span>
        <span class="infra-badge-state state-green">정상</span>
      </div>
      <div class="infra-badge-item">
        <span class="infra-badge-name">AWS DR</span>
        <span class="infra-badge-state state-amber" title="AWS는 Standby 상태가 정상 가동입니다.">Standby(정상)</span>
      </div>
    </div>

    <!-- NAVIGATION & LOGOUT -->
    <div class="header-right">
      <div class="fs-ctl" role="group" aria-label="글자 크기" title="글자 크기 조절">
        <button type="button" class="fs-btn" onclick="figFont(-1)" aria-label="글자 작게">가−</button>
        <button type="button" class="fs-btn" onclick="figFont(0)" aria-label="글자 기본" title="기본으로">가</button>
        <button type="button" class="fs-btn" onclick="figFont(1)" aria-label="글자 크게">가+</button>
      </div>
      <a class="nav-btn" href="/">대시보드</a>
      <a class="nav-btn" href="/#cfg/">설계/설정</a>
      <a class="nav-btn" href="/#term/">콘솔</a>
      <a class="nav-btn active" href="/api/ai/hub">협업 허브</a>
      {user_header_html}
      <button type="button" class="logout-btn" id="logout-btn" onclick="hubLogout()" title="로그아웃">로그아웃</button>
    </div>
  </header>

  <!-- 2. 메인 워크스페이스 레이아웃 (이메일 클라이언트 형태: 전체 사서함 > 수신함 / 발신함 계단식 아코디언) -->
  <div class="hub-container">
    <!-- 좌측 사이드바: 전체 사서함 > 수신함/발신함 아코디언 및 계단식 트리 -->
    <aside class="hub-side hub-nav" id="hub-menu">
      <!-- 1. 전체 사서함 그룹 (아코디언/계단식) -->
      <div class="tree-group" id="group-mail">
        <div class="tree-root" onclick="toggleTreeGroup('mail')">
          <div class="tree-root-left">
            <span class="tree-arrow">▼</span>
            <span>전체 사서함</span>
          </div>
          <span class="badge-count">{dc_sum['total'] + len(shares)}</span>
        </div>
        <div class="tree-children" id="tree-mail-children">
          <!-- 수신함 (괄호 생략 및 계단식 하위 메뉴) -->
          <div class="tree-node">
            <button type="button" class="tree-node-head" id="side-node-inbox" data-pane="inbox" onclick="navTo('inbox', 'list')">
              <span>수신함</span>
              <span class="badge-count badge-warn">{dc_sum['tasks_open']}</span>
            </button>
            <div class="tree-sub-children">
              <button type="button" class="tree-leaf" id="leaf-inbox-list" data-pane="inbox-list" onclick="navTo('inbox', 'list')">
                <span>과제 목록</span>
                <span style="font-size:10.5px;color:#64748b;">{dc_sum['total']}</span>
              </button>
              <button type="button" class="tree-leaf" id="leaf-inbox-create" data-pane="inbox-create" onclick="navTo('inbox', 'create')">
                <span>신규 접수</span>
              </button>
            </div>
          </div>

          <!-- 발신함 (괄호 생략 및 계단식 하위 메뉴) -->
          <div class="tree-node">
            <button type="button" class="tree-node-head" id="side-node-dispatch" data-pane="dispatch" onclick="navTo('dispatch', 'form')">
              <span>발신함</span>
              <span class="badge-count">{len(shares)}</span>
            </button>
            <div class="tree-sub-children">
              <button type="button" class="tree-leaf" id="leaf-dispatch-form" data-pane="dispatch-form" onclick="navTo('dispatch', 'form')">
                <span>상황 작성</span>
              </button>
              <button type="button" class="tree-leaf" id="leaf-dispatch-feed" data-pane="dispatch-feed" onclick="navTo('dispatch', 'feed')">
                <span>공유 내역</span>
                <span style="font-size:10.5px;color:#64748b;">{len(shares)}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. 공동 목표 및 AI 그룹 -->
      <div class="tree-group" id="group-goals">
        <div class="tree-root" onclick="toggleTreeGroup('goals')">
          <div class="tree-root-left">
            <span class="tree-arrow">▼</span>
            <span>공동 목표 및 AI</span>
          </div>
          <span class="badge-count">{gs['done']}/{gs['total']}</span>
        </div>
        <div class="tree-children" id="tree-goals-children">
          <button type="button" class="tree-leaf" id="leaf-goals-board" onclick="navTo('goals', 'board')">
            <span>목표 보드</span>
            <span style="font-size:10.5px;color:#10b981;font-weight:700;">{gs['percent']}%</span>
          </button>
          <button type="button" class="tree-leaf" id="leaf-goals-ai" onclick="navTo('goals', 'ai')">
            <span>AI 연계</span>
          </button>
        </div>
      </div>

      <!-- 3. 포털 변경 이력 그룹 -->
      <div class="tree-group" id="group-portal">
        <div class="tree-root" onclick="toggleTreeGroup('portal')">
          <div class="tree-root-left">
            <span class="tree-arrow">▼</span>
            <span>포털 변경 이력</span>
          </div>
          <span class="badge-count">{len(ch_list)}</span>
        </div>
        <div class="tree-children" id="tree-portal-children">
          <button type="button" class="tree-leaf" id="leaf-portal-log" onclick="navTo('portal', 'log')">
            <span>감사 로그</span>
            <span style="font-size:10.5px;color:#64748b;">{len(ch_list)}</span>
          </button>
        </div>
      </div>
    </aside>

    <!-- 우측 본문 (바디에 나눠진 작업을 작업 메뉴로 분리) -->
    <main class="hub-content">
      {err_html}{notice_html}

      <!-- [섹션 1] 수신 과제함 (Discord ➔ Web) -->
      <section class="pane" id="pane-inbox">
        <div class="pane-header">
          <h1 class="pane-title">Discord 멘션 수신함</h1>
          <p class="pane-desc">Discord #figteaminfra 채널에서 들어온 확인 요청 및 공유 사항을 한곳에서 관리합니다.</p>
        </div>

        <!-- 바디 작업 메뉴 1: 수신 과제 목록 / 신규 과제 접수 -->
        <div class="task-nav-bar" id="inbox-task-nav">
          <button type="button" class="task-tab-btn active" data-task="list" onclick="switchTaskView('inbox', 'list')">수신 과제 목록 ({dc_sum['total']})</button>
          <button type="button" class="task-tab-btn" data-task="create" onclick="switchTaskView('inbox', 'create')">신규 과제 수동 접수</button>
        </div>

        <!-- 작업 1-A: 수신 과제 목록 -->
        <div class="task-view active" id="inbox-view-list">
          <div class="kpi-row">
            <div class="kpi-box"><div class="kpi-title">전체 접수</div><div class="kpi-val">{dc_sum['total']}건</div></div>
            <div class="kpi-box" style="border-left:3px solid #f59e0b;"><div class="kpi-title" style="color:#fde68a;">미처리 과제</div><div class="kpi-val" style="color:#fde68a;">{dc_sum['tasks_open']}건</div></div>
            <div class="kpi-box" style="border-left:3px solid #3b82f6;"><div class="kpi-title">진행중</div><div class="kpi-val">{dc_sum['tasks_in_progress']}건</div></div>
            <div class="kpi-box" style="border-left:3px solid #10b981;"><div class="kpi-title">처리완료</div><div class="kpi-val">{dc_sum['tasks_done']}건</div></div>
            <div class="kpi-box" style="border-left:3px solid #38bdf8;"><div class="kpi-title">공유 정보</div><div class="kpi-val">{dc_sum['shares']}건</div></div>
          </div>

          <div class="filter-pills">
            <a class="filter-pill" href="/api/ai/hub?tab=inbox&amp;dc_filter=all">전체 ({dc_sum['total']})</a>
            <a class="filter-pill" href="/api/ai/hub?tab=inbox&amp;dc_filter=task">처리할 과제 ({dc_sum['tasks_total']})</a>
            <a class="filter-pill" href="/api/ai/hub?tab=inbox&amp;dc_filter=open_task">미처리 과제 ({dc_sum['tasks_open'] + dc_sum['tasks_in_progress']})</a>
            <a class="filter-pill" href="/api/ai/hub?tab=inbox&amp;dc_filter=share">공유 ({dc_sum['shares']})</a>
          </div>

          {discord_inbox_html}
        </div>

        <!-- 작업 1-B: 신규 과제 수동 접수 -->
        <div class="task-view" id="inbox-view-create">
          <div class="form-panel">
            <h2 style="font-size:14px;color:#fff;margin:0 0 4px;">신규 과제 또는 멘션 수동 접수</h2>
            <p style="font-size:12px;color:#94a3b8;margin:0 0 12px;">회의 중 발생한 인프라 과제나 점검 사항을 웹에서 직접 등록하면 디스코드에 알림이 전송됩니다.</p>
            <form method="post" action="/api/ai/hub/discord-ingest">
              <input type="hidden" name="tab" value="inbox">
              <div class="form-row">
                <div><label class="form-label">채널</label><input type="text" name="channel" value="figteaminfra" maxlength="60"></div>
                <div><label class="form-label">구분</label><select name="category"><option value="">자동 구분</option><option value="task">처리할 과제</option><option value="share">공유 정보</option></select></div>
              </div>
              <div class="form-group">
                <label class="form-label">내용 (#figteaminfra 멘션 포함)</label>
                <textarea name="content" required placeholder="예: #figteaminfra KT Edge 502 에러 간헐 발생 점검 필요"></textarea>
              </div>
              <button type="submit" class="btn-submit">과제 접수 및 Discord 알림</button>
            </form>
          </div>
        </div>
      </section>

      <!-- [섹션 2] 상황 공유 발신 (Web ➔ Discord) -->
      <section class="pane" id="pane-dispatch">
        <div class="pane-header">
          <h1 class="pane-title">팀 상황 공유 발신</h1>
          <p class="pane-desc">인프라 작업 결과나 점검 내용을 작성하면 Discord 채널로 실시간 알림이 발송되고 팀 피드에 기록됩니다.</p>
        </div>

        <!-- 바디 작업 메뉴 2: 상황 공유 작성 / 최근 공유 내역 -->
        <div class="task-nav-bar" id="dispatch-task-nav">
          <button type="button" class="task-tab-btn active" data-task="form" onclick="switchTaskView('dispatch', 'form')">상황 공유 작성 및 발신</button>
          <button type="button" class="task-tab-btn" data-task="feed" onclick="switchTaskView('dispatch', 'feed')">최근 팀 공유 내역 ({len(shares)})</button>
        </div>

        <!-- 작업 2-A: 상황 공유 작성 -->
        <div class="task-view active" id="dispatch-view-form">
          <div class="form-panel">
            <form method="post" action="/api/ai/hub">
              <input type="hidden" name="tab" value="dispatch">
              
              <div class="form-group">
                <label class="form-label">대상 인프라 영역 (아래 버튼을 누르면 자동 입력됩니다)</label>
                <div class="quick-chips">
                  <button type="button" class="chip-btn" onclick="setArea('inst-ktedge/nginx')">KT Edge (Nginx)</button>
                  <button type="button" class="chip-btn" onclick="setArea('inst-cp1/k8s')">k8s 마스터 (cp1)</button>
                  <button type="button" class="chip-btn" onclick="setArea('inst-db01/mysql')">MySQL DB (db-01)</button>
                  <button type="button" class="chip-btn" onclick="setArea('inst-awsdr/dr')">AWS DR (Warm-Standby)</button>
                  <button type="button" class="chip-btn" onclick="setArea('network/wireguard')">WireGuard 풀메쉬</button>
                  <button type="button" class="chip-btn" onclick="setArea('openstack/core')">OpenStack Core</button>
                  <button type="button" class="chip-btn" onclick="setArea('general')">일반 공통</button>
                </div>
              </div>

              <div class="form-row">
                <div><label class="form-label">영역 코드</label><input type="text" id="dispatch-area" name="area" value="{esc(prefill.get('area') or 'general')}" maxlength="60"></div>
                <div><label class="form-label">진행 상태</label><select name="status">{options_html}</select></div>
              </div>

              <div class="form-row">
                <div><label class="form-label">연계 목표 (선택)</label><select name="goal_id">{goal_select_html}</select></div>
                <div><label class="form-label">연계 목표 상태 변경 (선택)</label><select name="goal_status">{"".join(g_st_opts)}</select></div>
              </div>

              <div class="form-group">
                <label class="form-label">제목</label>
                <input type="text" name="title" value="{esc(prefill.get('title') or '')}" placeholder="예: k3s flannel 10.42.0.0/16 서브넷 점검 완료" maxlength="120">
              </div>

              <div class="form-group">
                <label class="form-label">작업 내용 요약</label>
                <textarea name="summary" required placeholder="수행한 작업 내용, 변경 파라미터, 확인된 수치를 입력하세요.">{esc(prefill.get('summary') or '')}</textarea>
              </div>

              <div class="form-row">
                <div><label class="form-label">타 영역 확인 요청 (선택)</label><input type="text" name="check_request" value="{esc(prefill.get('check_request') or '')}" placeholder="예: AWS DR 담당자 ch_dr 확인 부탁드립니다" maxlength="400"></div>
                <div><label class="form-label">관련 포털 URL (선택)</label><input type="text" name="cfg_url" value="{esc(prefill.get('cfg_url') or '')}" placeholder="예: https://figteam.ktci5.kr/#cfg/inst-db01" maxlength="300"></div>
              </div>

              <button type="submit" class="btn-submit">Discord 공유 및 팀 피드 기록</button>
            </form>
          </div>
        </div>

        <!-- 작업 2-B: 최근 공유 내역 -->
        <div class="task-view" id="dispatch-view-feed">
          <div style="margin-bottom:12px;font-size:13.5px;font-weight:700;color:#fff;">최근 팀 공유 내역</div>
          {feed_html}
        </div>
      </section>

      <!-- [섹션 3] 팀 공동 목표 및 AI -->
      <section class="pane" id="pane-goals">
        <div class="pane-header">
          <h1 class="pane-title">팀 공동 목표 및 AI 연계</h1>
          <p class="pane-desc">인프라 목표 달성률을 추적하고, ChatGPT, Claude, Gemini에 현재 인프라 현황을 원클릭으로 주입합니다.</p>
        </div>

        <!-- 바디 작업 메뉴 3: 공동 목표 보드 / AI 연계 -->
        <div class="task-nav-bar" id="goals-task-nav">
          <button type="button" class="task-tab-btn active" data-task="board" onclick="switchTaskView('goals', 'board')">공동 목표 보드 ({gs['done']}/{gs['total']})</button>
          <button type="button" class="task-tab-btn" data-task="ai" onclick="switchTaskView('goals', 'ai')">AI 프롬프트 1-Click 연계</button>
        </div>

        <!-- 작업 3-A: 공동 목표 보드 -->
        <div class="task-view active" id="goals-view-board">
          <div class="form-panel">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <h2 style="font-size:14.5px;color:#fff;margin:0;">공동 목표 보드 (달성 {gs['done']}/{gs['total']} · {gs['percent']}%)</h2>
              <span style="font-weight:900;color:#10b981;font-size:15px;">{gs['percent']}%</span>
            </div>
            <div class="prog-bar"><div class="prog-fill" style="width:{gs['percent']}%;"></div></div>

            {goals_board_html}

            <details style="margin-top:16px;">
              <summary style="cursor:pointer;font-weight:700;color:#93c5fd;font-size:13px;">+ 신규 공동 목표 추가</summary>
              <form method="post" action="/api/ai/hub/goal" style="margin-top:12px;">
                <input type="hidden" name="tab" value="goals">
                <div class="form-row">
                  <div><label class="form-label">목표 제목</label><input type="text" name="title" placeholder="예: 3사 DR 자동 절체 리허설 성공" maxlength="120" required></div>
                  <div><label class="form-label">대상 영역</label><input type="text" name="area" value="{esc(prefill.get('area') or 'general')}" maxlength="60"></div>
                </div>
                <div class="form-row">
                  <div><label class="form-label">담당자</label><input type="text" name="owner" value="{member_name}" placeholder="담당자 이름" maxlength="40"></div>
                  <div><label class="form-label">기한</label><input type="text" name="target_date" placeholder="예: 2026-11-30" maxlength="20"></div>
                </div>
                <div class="form-group">
                  <label class="form-label">완료 기준 및 검증 메모</label>
                  <input type="text" name="note" placeholder="예: ch_dr 지연 0초 및 200 OK 확인" maxlength="600">
                </div>
                <button type="submit" class="btn-submit">목표 등록 및 알림</button>
              </form>
            </details>
          </div>
        </div>

        <!-- 작업 3-B: AI 연계 -->
        <div class="task-view" id="goals-view-ai">
          <div class="form-panel">
            <h2 style="font-size:14px;color:#fff;margin:0 0 6px;">3대 AI 채팅 1-Click 연계</h2>
            <p style="font-size:12px;color:#94a3b8;margin:0 0 12px;">현재 인프라 상태와 목표 브리핑을 AI 창으로 자동 전달합니다.</p>
            
            <div class="form-group">
              <label class="form-label">집중 공동 목표 선택</label>
              <select id="hub-focus-goal">{goal_select_html}</select>
            </div>

            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button type="button" class="btn-submit" style="background:#059669;padding:8px 14px;font-size:12.5px;" onclick="launchAi('chatgpt')">ChatGPT로 열기</button>
              <button type="button" class="btn-submit" style="background:#d97706;padding:8px 14px;font-size:12.5px;" onclick="launchAi('claude')">Claude로 열기</button>
              <button type="button" class="btn-submit" style="background:#2563eb;padding:8px 14px;font-size:12.5px;" onclick="launchAi('gemini')">Gemini로 열기</button>
              <button type="button" class="act-btn" id="btn-copy-prompt" style="padding:8px 14px;font-size:12.5px;" onclick="launchAi('copy')">공통 프롬프트 복사</button>
            </div>
            <p id="hub-launch-msg" style="margin:10px 0 0;font-size:12px;color:#94a3b8;"></p>
            <textarea id="hub-fallback-prompt" readonly style="margin-top:10px;min-height:70px;font-size:12px;color:#94a3b8;{'display:none;' if not full_prompt_txt else ''}">{full_prompt_txt}</textarea>
          </div>
        </div>
      </section>

      <!-- [섹션 4] 포털 변경 감사로그 -->
      <section class="pane" id="pane-portal">
        <div class="pane-header">
          <h1 class="pane-title">포털(#cfg) 변경 이력</h1>
          <p class="pane-desc">설계/설정 포털에서 인프라 구성 및 문서가 변경될 때 기록되는 감사 로그입니다.</p>
        </div>
        {recent_changes_html}
      </section>
    </main>
  </div>

  <script>
    function setArea(val) {{
      const el = document.getElementById('dispatch-area');
      if (el) {{ el.value = val; el.focus(); }}
    }}

    function navTo(pane, task) {{
      switchHubTab(pane);
      if (task) switchTaskView(pane, task);
      updateActiveSidebar(pane, task);
    }}

    function toggleTreeGroup(id) {{
      const g = document.getElementById('group-' + id);
      if (g) g.classList.toggle('collapsed');
    }}

    function updateActiveSidebar(pane, task) {{
      document.querySelectorAll('.tree-node-head, .tree-leaf').forEach(el => el.classList.remove('active'));
      const node = document.getElementById('side-node-' + pane);
      if (node) node.classList.add('active');
      if (task) {{
        const leaf = document.getElementById('leaf-' + pane + '-' + task);
        if (leaf) leaf.classList.add('active');
      }}
    }}

    function switchHubTab(tabName) {{
      const valid = ['inbox', 'dispatch', 'goals', 'portal'];
      if (!valid.includes(tabName)) tabName = 'inbox';
      
      document.querySelectorAll('.pane').forEach(p => {{
        if (p.id === 'pane-' + tabName) {{
          p.classList.add('active');
        }} else {{
          p.classList.remove('active');
        }}
      }});

      try {{
        history.replaceState(null, '', '#' + tabName);
        localStorage.setItem('figteam_hub_tab', tabName);
      }} catch (e) {{}}
    }}

    // 바디 내 작업 메뉴 전환 함수
    function switchTaskView(paneName, taskName) {{
      const nav = document.getElementById(paneName + '-task-nav');
      if (nav) {{
        nav.querySelectorAll('.task-tab-btn').forEach(b => {{
          if (b.getAttribute('data-task') === taskName) {{
            b.classList.add('active');
          }} else {{
            b.classList.remove('active');
          }}
        }});
      }}
      const pane = document.getElementById('pane-' + paneName);
      if (pane) {{
        pane.querySelectorAll('.task-view').forEach(v => {{
          if (v.id === paneName + '-view-' + taskName) {{
            v.classList.add('active');
          }} else {{
            v.classList.remove('active');
          }}
        }});
      }}
      updateActiveSidebar(paneName, taskName);
    }}

    // 탑 헤더 실시간 시계 연동
    function updateClock() {{
      const d = new Date();
      const pad = n => String(n).padStart(2, '0');
      const s = `${{d.getFullYear()}}-${{pad(d.getMonth()+1)}}-${{pad(d.getDate())}} ${{pad(d.getHours())}}:${{pad(d.getMinutes())}}:${{pad(d.getSeconds())}} KST`;
      const el = document.getElementById('current-clock');
      if (el) el.textContent = s;
    }}
    setInterval(updateClock, 1000);
    updateClock();

    // 탑 헤더 글자 크기 조절 (포털과 localStorage.fig.fs 100% 동일 연동)
    var FIG_FS = [0.85, 0.925, 1, 1.1, 1.25, 1.4], FIG_FS_BASE = 2;
    function figFont(dir) {{
      var i;
      try {{ i = parseInt(localStorage.getItem('fig.fs'), 10); }} catch (e) {{}}
      if (isNaN(i)) i = FIG_FS_BASE;
      if (dir === 1) i = Math.min(FIG_FS.length - 1, i + 1);
      else if (dir === -1) i = Math.max(0, i - 1);
      else if (dir === 0) i = FIG_FS_BASE;
      try {{ localStorage.setItem('fig.fs', i); }} catch (e) {{}}
      var z = FIG_FS[i];
      var el = document.querySelector('.hub-container');
      if (el) el.style.zoom = z;
    }}
    window.addEventListener('load', function () {{ setTimeout(function () {{ figFont(); }}, 50); }});

    // 로그아웃 (포털 세션, 콘솔 락, 위키 토큰 일괄 초기화 후 포털 메인으로 이동)
    async function hubLogout() {{
      try {{
        sessionStorage.removeItem('figteam_auth_token');
        sessionStorage.removeItem('fig.auth');
        localStorage.removeItem('fig.term.user');
        await fetch('/console/api/lock', {{ method: 'POST', credentials: 'same-origin' }}).catch(() => {{}});
        await fetch('/api/logout', {{ method: 'POST', credentials: 'same-origin' }}).catch(() => {{}});
      }} catch (e) {{}}
      window.location.href = '/';
    }}

    // 자동 이름 연동 (포털에서 1회 설정된 이름을 읽어 허브 세션 자동 생성)
    async function checkAutoSync() {{
      const isLoggedIn = {"true" if is_logged_in else "false"};
      if (isLoggedIn) return;
      try {{
        let name = (localStorage.getItem('fig.term.user') || '').trim();
        if (!name) {{
          const pRaw = localStorage.getItem('fig.access.profile_v1');
          if (pRaw) {{
            const p = JSON.parse(pRaw);
            name = (p.member || '').trim();
          }}
        }}
        if (name) {{
          const res = await fetch('/api/ai/hub/auto-login', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ member: name }})
          }});
          if (res.ok) {{
            location.reload();
          }}
        }}
      }} catch (e) {{}}
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      checkAutoSync();
      const default_tab = "{default_tab}";
      let t = default_tab;
      let task = "";
      const h = (window.location.hash || '').replace('#', '').trim();
      if (h.includes('-')) {{
        const parts = h.split('-');
        if (['inbox', 'dispatch', 'goals', 'portal'].includes(parts[0])) {{
          t = parts[0];
          task = parts.slice(1).join('-');
        }}
      }} else if (['inbox', 'dispatch', 'goals', 'portal'].includes(h)) {{
        t = h;
      }} else {{
        try {{
          const saved = localStorage.getItem('figteam_hub_tab');
          if (['inbox', 'dispatch', 'goals', 'portal'].includes(saved)) t = saved;
        }} catch(e) {{}}
      }}
      if (!task) {{
        if (t === 'inbox') task = 'list';
        else if (t === 'dispatch') task = 'form';
        else if (t === 'goals') task = 'board';
        else if (t === 'portal') task = 'log';
      }}
      navTo(t, task);
    }});

    async function launchAi(target) {{
      const msgEl = document.getElementById('hub-launch-msg');
      const goalSel = document.getElementById('hub-focus-goal');
      const gid = goalSel ? goalSel.value : '';
      let fullPrompt = document.getElementById('hub-fallback-prompt')?.value || '';
      let shortPrompt = fullPrompt.slice(0, 900);
      try {{
        const res = await fetch('/api/ai/prompt' + (gid ? '?goal_id=' + encodeURIComponent(gid) : ''), {{ credentials: 'same-origin', cache: 'no-store' }});
        if (!res.ok) throw new Error('먼저 팀 로그인을 완료해 주세요.');
        const data = await res.json();
        fullPrompt = data.prompt || fullPrompt;
        shortPrompt = data.short_prompt || shortPrompt;
        const fb = document.getElementById('hub-fallback-prompt');
        if (fb) {{ fb.value = fullPrompt; fb.style.display = 'block'; }}
        if (navigator.clipboard && navigator.clipboard.writeText) {{
          await navigator.clipboard.writeText(fullPrompt);
        }}
      }} catch (e) {{
        msgEl.textContent = '경고: ' + (e.message || '로그인이 필요합니다.');
        return;
      }}
      if (target === 'copy') {{
        msgEl.textContent = '공통 프롬프트를 클립보드에 복사했습니다. AI 앱에 붙여넣으세요.';
        return;
      }}
      const q = encodeURIComponent(shortPrompt);
      if (target === 'chatgpt') {{
        window.open('https://chatgpt.com/?q=' + q, '_blank', 'noopener');
        msgEl.textContent = 'ChatGPT 창을 열었습니다. 필요 시 클립보드의 전체 브리핑을 붙여넣으세요.';
      }} else if (target === 'claude') {{
        window.open('https://claude.ai/new?q=' + q, '_blank', 'noopener');
        msgEl.textContent = 'Claude 창을 열었습니다. 필요 시 클립보드의 전체 브리핑을 붙여넣으세요.';
      }} else if (target === 'gemini') {{
        window.open('https://gemini.google.com/app', '_blank', 'noopener');
        msgEl.textContent = 'Gemini 창을 열었습니다. 클립보드의 전체 브리핑을 붙여넣어 시작하세요.';
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
