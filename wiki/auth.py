"""팀·세션 (스펙 6.3)."""
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass

from wiki.errors import ApiError

ITERATIONS = 600_000
SESSION_TTL = 7 * 24 * 3600
COOKIE = "fw_s"
SLUG_RE = re.compile(r"^[a-z0-9-]{3,32}$")
WINDOW, MAX_FAILS = 600, 10


@dataclass
class Session:
    team_id: int
    slug: str
    team_name: str
    member: str


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return h, salt


def verify_password(password, pw_hash, salt):
    return hmac.compare_digest(hash_password(password, salt)[0], pw_hash)


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def check_member(member):
    if not isinstance(member, str) or not (1 <= len(member.strip()) <= 20):
        raise ApiError(422, "이름은 1~20자로 입력하세요", {"field": "member"})
    return member.strip()


def check_password(pw, field="password"):
    if not isinstance(pw, str) or len(pw) < 6:
        raise ApiError(422, "비밀번호는 6자 이상이어야 합니다", {"field": field})
    return pw


def rate_check(conn, key):
    now = int(time.time())
    row = conn.execute("SELECT count, window_start FROM login_attempts WHERE key=?", (key,)).fetchone()
    if row and now - row["window_start"] < WINDOW and row["count"] >= MAX_FAILS:
        raise ApiError(429, "시도가 많습니다. 10분 뒤 다시 시도하세요")


def rate_fail(conn, key):
    now = int(time.time())
    row = conn.execute("SELECT count, window_start FROM login_attempts WHERE key=?", (key,)).fetchone()
    if not row or now - row["window_start"] >= WINDOW:
        conn.execute("INSERT OR REPLACE INTO login_attempts(key, count, window_start) VALUES(?,?,?)", (key, 1, now))
    else:
        conn.execute("UPDATE login_attempts SET count=count+1 WHERE key=?", (key,))


def new_session(conn, team_id, member):
    token = secrets.token_urlsafe(32)
    conn.execute("INSERT INTO sessions(token_hash, team_id, member, expires_at) VALUES(?,?,?,?)",
                 (_token_hash(token), team_id, member, int(time.time()) + SESSION_TTL))
    return token


def create_team(conn, data, create_code, client_key):
    slug = data.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ApiError(422, "팀 주소는 영문 소문자·숫자·- 3~32자입니다", {"field": "slug"})
    name = data.get("name")
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 40):
        raise ApiError(422, "팀 이름은 1~40자로 입력하세요", {"field": "name"})
    member = check_member(data.get("member"))
    pw = check_password(data.get("password"))
    key = "create|" + client_key
    rate_check(conn, key)
    code = data.get("create_code") or ""
    if not create_code or not hmac.compare_digest(str(code), create_code):
        rate_fail(conn, key)
        raise ApiError(403, "팀 생성 암호가 맞지 않습니다")
    if conn.execute("SELECT 1 FROM teams WHERE slug=?", (slug,)).fetchone():
        raise ApiError(409, "이미 있는 팀 주소입니다")
    h, salt = hash_password(pw)
    cur = conn.execute("INSERT INTO teams(slug, name, pw_hash, pw_salt, created_at) VALUES(?,?,?,?,?)",
                       (slug, name.strip(), h, salt, int(time.time())))
    return new_session(conn, cur.lastrowid, member)


def login(conn, data, client_key):
    slug = data.get("slug") if isinstance(data.get("slug"), str) else ""
    member = check_member(data.get("member"))
    key = slug + "|" + client_key
    rate_check(conn, key)
    row = conn.execute("SELECT id, pw_hash, pw_salt FROM teams WHERE slug=?", (slug,)).fetchone()
    pw = data.get("password") if isinstance(data.get("password"), str) else ""
    if not row or not verify_password(pw, row["pw_hash"], row["pw_salt"]):
        rate_fail(conn, key)
        raise ApiError(401, "팀 주소나 비밀번호가 맞지 않습니다")
    conn.execute("DELETE FROM login_attempts WHERE key=?", (key,))
    return new_session(conn, row["id"], member)


def get_session(conn, token):
    if not token:
        return None
    row = conn.execute(
        "SELECT s.team_id, s.member, s.expires_at, t.slug, t.name FROM sessions s JOIN teams t ON t.id=s.team_id "
        "WHERE s.token_hash=?", (_token_hash(token),)).fetchone()
    if not row or row["expires_at"] < time.time():
        return None
    return Session(row["team_id"], row["slug"], row["name"], row["member"])


def logout(conn, token):
    if token:
        conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))


def change_password(conn, session, data):
    row = conn.execute("SELECT pw_hash, pw_salt FROM teams WHERE id=?", (session.team_id,)).fetchone()
    if not verify_password(str(data.get("current") or ""), row["pw_hash"], row["pw_salt"]):
        raise ApiError(401, "현재 비밀번호가 맞지 않습니다", {"field": "current"})
    h, salt = hash_password(check_password(data.get("new"), "new"))
    conn.execute("UPDATE teams SET pw_hash=?, pw_salt=? WHERE id=?", (h, salt, session.team_id))
    conn.execute("DELETE FROM sessions WHERE team_id=?", (session.team_id,))


def reset_password(conn, slug, new_password):
    h, salt = hash_password(check_password(new_password))
    cur = conn.execute("UPDATE teams SET pw_hash=?, pw_salt=? WHERE slug=?", (h, salt, slug))
    if cur.rowcount == 0:
        raise ApiError(404, "없는 팀입니다")
    conn.execute("DELETE FROM sessions WHERE team_id=(SELECT id FROM teams WHERE slug=?)", (slug,))
