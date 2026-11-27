"""콘솔 잠금: 비밀번호 해시와 세션(12시간).

세션은 파일에 sha256(토큰)->만료시각 으로만 저장해 서비스 재시작에도 유지한다.
IP 고정은 하지 않는다 — Cloudflare 경유 시 같은 브라우저도 IPv4/IPv6 가 번갈아 잡혀
매번 잠금이 다시 뜨기 때문. 쿠키는 HttpOnly·Secure·SameSite=Strict.
"""
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import time

ITERATIONS = 600_000
TTL = 12 * 3600   # 사이트 첫 로그인 한 번으로 12시간 (대시보드·설정·콘솔 공통)
WINDOW, MAX_FAILS = 600, 5


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex(), salt


class Lock:
    def __init__(self, pw_hash, salt, store=None):
        self.pw_hash, self.salt = pw_hash or "", salt or "00" * 16
        self.store = pathlib.Path(store) if store else None
        self.sessions = self._load()   # sha256(token) -> expires
        self.fails = {}                # ip -> (count, window_start)

    def _load(self):
        try:
            data = json.loads(self.store.read_text(encoding="utf-8")) if self.store else {}
            now = time.time()
            return {k: float(v) for k, v in data.items() if float(v) > now}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _save(self):
        if not self.store:
            return
        now = time.time()
        self.sessions = {k: v for k, v in self.sessions.items() if v > now}
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f)
            os.replace(tmp, self.store)
        except OSError:
            pass   # 저장 실패해도 메모리 세션으로 계속 동작

    def _key(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def limited(self, ip):
        n, start = self.fails.get(ip, (0, 0))
        return time.time() - start < WINDOW and n >= MAX_FAILS

    def unlock(self, password, ip):
        """맞으면 토큰, 틀리면 None. 비밀번호가 설정되지 않았으면 항상 실패."""
        ok = bool(self.pw_hash) and hmac.compare_digest(hash_password(password or "", self.salt)[0], self.pw_hash)
        if not ok:
            n, start = self.fails.get(ip, (0, 0))
            if time.time() - start >= WINDOW:
                n, start = 0, time.time()
            self.fails[ip] = (n + 1, start)
            return None
        self.fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        self.sessions[self._key(token)] = time.time() + TTL
        self._save()
        return token

    def check(self, token, ip=None):
        """ip 는 호환용 인자 — 세션을 IP 에 묶지 않는다."""
        if not token:
            return False
        exp = self.sessions.get(self._key(token))
        return bool(exp) and exp > time.time()

    def lock(self, token):
        if token:
            if self.sessions.pop(self._key(token), None) is not None:
                self._save()
