"""재접속 세션 허브.

살아 있는 셸(PtySession)을 WS 가 끊겨도 (이름, 대상) 키로 s1 메모리에 유지하고,
스크롤백 버퍼를 모아 두었다가 다시 붙을 때 재생해 화면을 복원한다.
메타정보(이름·대상·마지막 명령·시각)는 store(Redis)에 베스트에포트로 기록한다.
Redis 가 없거나 실패해도 터미널 자체는 그대로 동작한다.
"""
import re
import time

OWNER_RE = re.compile(r"[^0-9A-Za-z가-힣._ -]")
MAX_OWNER = 24
BUF_CAP = 200_000          # 스크롤백 상한(문자)
MAX_CMD = 200


def clean_owner(s):
    """사용자 이름 정리: 허용 문자만, 24자, 비면 guest."""
    s = OWNER_RE.sub("", (s or "").strip())[:MAX_OWNER].strip()
    return s or "guest"


class Live:
    """살아 있는 세션 하나. pty 는 실제 PtySession(테스트에선 None)."""

    def __init__(self, owner, target_id, pty=None, log=None):
        self.owner, self.target_id, self.pty, self.log = owner, target_id, pty, log
        self.buf = ""          # 스크롤백(출력 누적)
        self.ws = None         # 현재 붙은 WebSocket (없으면 분리됨)
        self.last_cmd = ""
        self._line = ""        # 입력 누적(엔터 전까지)
        self.started = time.time()
        self.last_at = self.started

    def append_out(self, text):
        self.buf += text
        if len(self.buf) > BUF_CAP:
            self.buf = self.buf[-BUF_CAP:]
        self.last_at = time.time()

    def feed_in(self, text):
        self.last_at = time.time()
        for ch in text:
            if ch in "\r\n":
                c = self._line.strip()
                if c:
                    self.last_cmd = c[:MAX_CMD]
                self._line = ""
            elif ch in ("\x7f", "\b"):
                self._line = self._line[:-1]
            elif ch >= " ":
                self._line += ch

    def meta(self):
        return {"owner": self.owner, "target": self.target_id, "last_cmd": self.last_cmd,
                "started": int(self.started), "last_at": int(self.last_at),
                "attached": self.ws is not None}


class SessionHub:
    def __init__(self, store=None):
        self.live = {}         # (owner, target) -> Live
        self.store = store

    def get(self, owner, target):
        return self.live.get((owner, target))

    def create(self, owner, target, pty=None, log=None):
        s = Live(owner, target, pty, log)
        self.live[(owner, target)] = s
        self.save(s)
        return s

    def drop(self, s):
        self.live.pop((s.owner, s.target_id), None)
        if self.store:
            try:
                self.store.drop(s.owner, s.target_id)
            except Exception:
                pass

    def list(self, owner):
        return [s for (o, _), s in self.live.items() if o == owner]

    def save(self, s):
        if not self.store:
            return
        try:
            self.store.touch(s.owner, s.target_id, s.last_cmd, s.started, s.last_at)
        except Exception:
            pass
