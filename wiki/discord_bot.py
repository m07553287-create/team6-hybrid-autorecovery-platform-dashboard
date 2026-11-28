"""Discord 채널의 #figteaminfra 멘션 메시지를 폴링해 figteam 위키 수신함(/api/discord/inbound)으로 전달한다.

외부 패키지 없이 Python 표준 라이브러리만 사용한다.
필수 환경변수:
  FIGTEAM_DISCORD_BOT_TOKEN    Discord Bot Token
  FIGTEAM_DISCORD_CHANNEL_IDS  감시할 Discord 채널 ID 목록 (쉼표 구분)
선택 환경변수:
  FIGTEAM_WIKI_URL             위키 API 주소 (기본: http://127.0.0.1:8080)
  FIGTEAM_INTERNAL_KEY         /api/discord/inbound X-Internal-Key
  FIGTEAM_DISCORD_POLL_SECONDS 폴링 주기 초 (기본: 5)
  FIGTEAM_DISCORD_STATE_FILE   마지막 처리 메시지 ID 저장 파일
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

from wiki.collab import has_figteam_trigger

DISCORD_API = "https://discord.com/api/v10"


def _http_json(url: str, headers: dict[str, str], body: dict | None = None, timeout: int = 8):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _load_state(path: pathlib.Path) -> dict[str, str]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:  # noqa: BLE001
        pass
    return {}


def _save_state(path: pathlib.Path, state: dict[str, str]) -> None:
    try:
        path.write_text(json.dumps(state), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def poll_once(
    bot_token: str,
    channel_ids: list[str],
    wiki_url: str,
    internal_key: str,
    state: dict[str, str],
) -> int:
    d_headers = {"Authorization": f"Bot {bot_token}", "User-Agent": "figteam-discord-bridge/1.0"}
    w_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "X-Internal-Key": internal_key,
    }
    sent = 0
    for cid in channel_ids:
        last_id = state.get(cid)
        qs = f"after={last_id}&limit=50" if last_id else "limit=10"
        msgs = _http_json(f"{DISCORD_API}/channels/{cid}/messages?{qs}", d_headers)
        if not isinstance(msgs, list) or not msgs:
            continue
        msgs_sorted = sorted(msgs, key=lambda m: int(m.get("id") or 0))
        if not last_id:
            # 최초 기동 시 과거 메시지 폭주를 막기 위해 마지막 커서만 기록
            state[cid] = str(msgs_sorted[-1]["id"])
            continue
        for msg in msgs_sorted:
            state[cid] = str(msg["id"])
            author_obj = msg.get("author") or {}
            if author_obj.get("bot"):
                continue
            content = str(msg.get("content") or "").strip()
            ref = msg.get("message_reference") or {}
            reply_to_msg_id = str(ref.get("message_id") or "")
            has_trigger = has_figteam_trigger(content)
            # 트리거 태그(#figteaminfra 등)가 있거나, 봇 메시지에 대한 '답장(Reply)'인 경우 모두 수집!
            if not content:
                continue
            if not has_trigger and not reply_to_msg_id:
                continue
            payload = {
                "team": os.environ.get("DEFAULT_TEAM_SLUG", "figteam"),
                "discord_message_id": str(msg["id"]),
                "reply_to_msg_id": reply_to_msg_id,
                "channel": f"ch-{cid[-6:]}",
                "author": author_obj.get("global_name") or author_obj.get("username") or "Discord",
                "content": content,
                "source": "discord_bot",
                "notify_discord": True,
            }
            _http_json(f"{wiki_url.rstrip('/')}/api/discord/inbound", w_headers, body=payload)
            sent += 1
    return sent


def main() -> int:
    token = os.environ.get("FIGTEAM_DISCORD_BOT_TOKEN", "").strip()
    channels = [c.strip() for c in os.environ.get("FIGTEAM_DISCORD_CHANNEL_IDS", "").split(",") if c.strip()]
    if not token or not channels:
        print("FIGTEAM_DISCORD_BOT_TOKEN 또는 FIGTEAM_DISCORD_CHANNEL_IDS 가 비어 있어 종료합니다.", file=sys.stderr)
        return 0
    wiki_url = os.environ.get("FIGTEAM_WIKI_URL", "http://127.0.0.1:8080")
    internal_key = os.environ.get("FIGTEAM_INTERNAL_KEY") or os.environ.get("FIGTEAM_AUTH_KEY") or "figteam-sec-2026-dr"
    poll_sec = max(2, int(os.environ.get("FIGTEAM_DISCORD_POLL_SECONDS", "5") or "5"))
    state_path = pathlib.Path(os.environ.get("FIGTEAM_DISCORD_STATE_FILE", "/tmp/figteam-discord-state.json"))

    state = _load_state(state_path)
    print(f"figteam-discord-bot started: channels={channels} poll={poll_sec}s", flush=True)
    while True:
        try:
            n = poll_once(token, channels, wiki_url, internal_key, state)
            _save_state(state_path, state)
            if n:
                print(f"ingested {n} discord message(s)", flush=True)
        except urllib.error.HTTPError as exc:
            print(f"discord http error: {exc.code}", file=sys.stderr, flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"discord poll error: {exc}", file=sys.stderr, flush=True)
        time.sleep(poll_sec)


if __name__ == "__main__":
    raise SystemExit(main())
