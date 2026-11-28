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
import re
import secrets
import time

ITERATIONS = 600_000
TTL = 12 * 3600   # 사이트 첫 로그인 한 번으로 12시간 (대시보드·설정·콘솔 공통)
KEY_COOKIE = "fc_k"
KEY_COOKIE_TTL = 365 * 24 * 3600
WINDOW, MAX_FAILS = 600, 5
ACCESS_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{2,16}$")
KEY_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_access_key(length=8):
    return "".join(secrets.choice(KEY_CHARS) for _ in range(length))


def normalize_access_key(key):
    if not isinstance(key, str):
        return ""
    s = key.strip().upper()
    return s if ACCESS_KEY_RE.match(s) else ""


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex(), salt


class Lock:
    def __init__(self, pw_hash, salt, store=None, require_key=True):
        self.pw_hash, self.salt = pw_hash or "", salt or "00" * 16
        self.store = pathlib.Path(store) if store else None
        self.registry_store = self.store.with_name("key_registry.json") if self.store else None
        self.require_key = bool(require_key)
        self.sessions = self._load()   # sha256(token) -> {exp, access_key, member}
        self.key_registry = self._load_registry()   # ak -> {access_key, member, names, ips, first_seen, last_seen, first_ip, last_ip, ua, login_count}
        self.fails = {}                # ip -> (count, window_start)

    def _load_registry(self):
        try:
            data = json.loads(self.registry_store.read_text(encoding="utf-8")) if self.registry_store else {}
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _save_registry(self):
        if not self.registry_store:
            return
        try:
            self.registry_store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.registry_store.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.key_registry, f, ensure_ascii=False)
            os.replace(tmp, self.registry_store)
        except OSError:
            pass

    def _record_key(self, ak, member, ip, ua=""):
        now = int(time.time())
        clean_member = str(member or "").strip()[:20] or "게스트"
        clean_ip = str(ip or "").strip()[:64]
        prev = self.key_registry.get(ak) or {}
        names = list(prev.get("names") or [])
        if clean_member != "게스트" and clean_member not in names:
            names.append(clean_member)
        ips = list(prev.get("ips") or [])
        if clean_ip and clean_ip not in ips:
            ips.append(clean_ip)
        self.key_registry[ak] = {
            "access_key": ak,
            "member": clean_member if clean_member != "게스트" else (prev.get("member") or "게스트"),
            "names": names[-20:],
            "ips": ips[-20:],
            "first_seen": int(prev.get("first_seen") or now),
            "last_seen": now,
            "first_ip": prev.get("first_ip") or clean_ip,
            "last_ip": clean_ip or prev.get("last_ip") or "",
            "ua": str(ua or prev.get("ua") or "")[:64],
            "login_count": int(prev.get("login_count") or 0) + 1,
        }
        self._save_registry()

    def _load(self):
        try:
            data = json.loads(self.store.read_text(encoding="utf-8")) if self.store else {}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}
        if not isinstance(data, dict):
            return {}
        now = time.time()
        out = {}
        dropped = False
        for k, v in data.items():
            if isinstance(v, dict):
                try:
                    exp = float(v.get("exp", 0))
                except (TypeError, ValueError):
                    dropped = True
                    continue
                ak = normalize_access_key(v.get("access_key", ""))
                mem = str(v.get("member") or "").strip()[:20]
            else:
                try:
                    exp = float(v)
                except (TypeError, ValueError):
                    dropped = True
                    continue
                ak = ""
                mem = ""
            if exp <= now:
                dropped = True
                continue
            if self.require_key and not ak:
                # 접속 키가 없는 이전 세션은 로드 시 즉시 만료한다
                dropped = True
                continue
            out[k] = {"exp": exp, "access_key": ak, "member": mem}
        if dropped and self.store:
            self.sessions = out
            self._save()
        return out

    def _save(self):
        if not self.store:
            return
        now = time.time()
        self.sessions = {
            k: v for k, v in self.sessions.items()
            if isinstance(v, dict) and float(v.get("exp", 0)) > now
        }
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.store.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.sessions, f, ensure_ascii=False)
            os.replace(tmp, self.store)
        except OSError:
            pass   # 저장 실패해도 메모리 세션으로 계속 동작

    def _key(self, token):
        return hashlib.sha256(token.encode()).hexdigest()

    def limited(self, ip):
        n, start = self.fails.get(ip, (0, 0))
        return time.time() - start < WINDOW and n >= MAX_FAILS

    def unlock(self, password, ip, access_key="", member="", ua=""):
        """비밀번호 검증 후 불변 접속 키를 자동 할당/유지해 세션을 연다."""
        ok = bool(self.pw_hash) and hmac.compare_digest(hash_password(password or "", self.salt)[0], self.pw_hash)
        if not ok:
            n, start = self.fails.get(ip, (0, 0))
            if time.time() - start >= WINDOW:
                n, start = 0, time.time()
            self.fails[ip] = (n + 1, start)
            return None
        ak = normalize_access_key(access_key) or generate_access_key()
        self.fails.pop(ip, None)
        token = secrets.token_urlsafe(32)
        clean_member = str(member or "").strip()[:20]
        self.sessions[self._key(token)] = {"exp": time.time() + TTL, "access_key": ak, "member": clean_member}
        self._save()
        self._record_key(ak, clean_member, ip, ua=ua)
        return token

    def session_key(self, token):
        status, info = self.check_detail(token)
        return info.get("access_key", "") if status == "ok" and info else ""

    def check_detail(self, token, ip=None):
        """세션 검증 결과 (status, info): 'ok' | 'no_key' | 'invalid'."""
        if not token:
            return "invalid", None
        sk = self._key(token)
        raw = self.sessions.get(sk)
        if not raw:
            return "invalid", None
        if isinstance(raw, dict):
            exp = float(raw.get("exp", 0))
            ak = normalize_access_key(raw.get("access_key", ""))
            info = {"exp": exp, "access_key": ak, "member": str(raw.get("member") or "")}
        else:
            exp = float(raw)
            ak = ""
            info = {"exp": exp, "access_key": "", "member": ""}
        if exp <= time.time():
            self.sessions.pop(sk, None)
            self._save()
            return "invalid", None
        if self.require_key and not ak:
            self.sessions.pop(sk, None)
            self._save()
            return "no_key", None
        return "ok", info

    def check(self, token, ip=None):
        """ip 는 호환용 인자 — 세션을 IP 에 묶지 않는다."""
        return self.check_detail(token, ip)[0] == "ok"

    def lock(self, token):
        if token:
            if self.sessions.pop(self._key(token), None) is not None:
                self._save()
