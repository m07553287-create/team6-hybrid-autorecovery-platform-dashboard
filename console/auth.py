"""콘솔 잠금: 비밀번호 해시와 메모리 세션(60분, IP 고정)."""
import hashlib
import hmac
import secrets
import time

ITERATIONS = 600_000
TTL = 3600
WINDOW, MAX_FAILS = 600, 5


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex(), salt


class Lock:
    def __init__(self, pw_hash, salt):
        self.pw_hash, self.salt = pw_hash or "", salt or "00" * 16
        self.sessions = {}   # sha256(token) -> (ip, expires)
        self.fails = {}      # ip -> (count, window_start)

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
        self.sessions[self._key(token)] = (ip, time.time() + TTL)
        return token

    def check(self, token, ip):
        if not token:
            return False
        v = self.sessions.get(self._key(token))
        if not v or v[1] < time.time() or v[0] != ip:
            return False
        return True

    def lock(self, token):
        if token:
            self.sessions.pop(self._key(token), None)
