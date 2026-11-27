"""팀·세션 (스펙 6.3) — Redis."""
import hashlib
import hmac
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
_DUMMY_SALT = "00" * 16


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


def _skey(token):
    return "fw:sess:" + hashlib.sha256(token.encode()).hexdigest()


def check_member(member):
    if not isinstance(member, str) or not (1 <= len(member.strip()) <= 20):
        raise ApiError(422, "이름은 1~20자로 입력하세요", {"field": "member"})
    return member.strip()


def check_password(pw, field="password"):
    if not isinstance(pw, str) or len(pw) < 6:
        raise ApiError(422, "비밀번호는 6자 이상이어야 합니다", {"field": field})
    return pw


def rate_check(r, key):
    n = r.get("fw:rl:" + key)
    if n and int(n) >= MAX_FAILS:
        raise ApiError(429, "시도가 많습니다. 10분 뒤 다시 시도하세요")


def rate_fail(r, key):
    k = "fw:rl:" + key
    if r.incr(k) == 1:   # Redis 6(우분투 22.04) 은 EXPIRE NX 가 없어 첫 실패 때만 만료를 건다
        r.expire(k, WINDOW)


def new_session(r, team_id, member):
    token = secrets.token_urlsafe(32)
    k = _skey(token)
    p = r.pipeline()
    p.hset(k, mapping={"team_id": team_id, "member": member})
    p.expire(k, SESSION_TTL)
    p.sadd(f"fw:sesslist:{team_id}", k)
    p.execute()
    return token


def create_team(r, data, create_code, client_key):
    slug = data.get("slug")
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise ApiError(422, "팀 주소는 영문 소문자·숫자·- 3~32자입니다", {"field": "slug"})
    name = data.get("name")
    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 40):
        raise ApiError(422, "팀 이름은 1~40자로 입력하세요", {"field": "name"})
    member = check_member(data.get("member"))
    pw = check_password(data.get("password"))
    key = "create|" + client_key
    rate_check(r, key)
    code = data.get("create_code") or ""
    if not create_code or not hmac.compare_digest(str(code), create_code):
        rate_fail(r, key)
        raise ApiError(403, "팀 생성 암호가 맞지 않습니다")
    team_id = add_team(r, slug, name.strip(), pw)
    return new_session(r, team_id, member)


def add_team(r, slug, name, password):
    """팀 레코드를 만든다(시드도 사용). 같은 주소가 있으면 409."""
    h, salt = hash_password(password)
    team_id = r.incr("fw:seq:team")
    created = r.hsetnx(f"fw:team:{slug}", "id", team_id)
    if not created:
        raise ApiError(409, "이미 있는 팀 주소입니다")
    r.hset(f"fw:team:{slug}", mapping={"slug": slug, "name": name, "pw_hash": h, "pw_salt": salt,
                                        "created_at": int(time.time())})
    r.set(f"fw:teamid:{team_id}", slug)
    return team_id


def login(r, data, client_key):
    slug = data.get("slug") if isinstance(data.get("slug"), str) else ""
    member = check_member(data.get("member"))
    key = slug + "|" + client_key
    rate_check(r, key)
    t = r.hgetall(f"fw:team:{slug}") if SLUG_RE.match(slug) else {}
    pw = data.get("password") if isinstance(data.get("password"), str) else ""
    # 없는 팀도 같은 시간 동안 해시를 계산해 응답 시간으로 팀 주소를 추측하지 못하게 한다
    ok = verify_password(pw, t.get("pw_hash", ""), t.get("pw_salt", _DUMMY_SALT)) and bool(t)
    if not ok:
        rate_fail(r, key)
        raise ApiError(401, "팀 주소나 비밀번호가 맞지 않습니다")
    r.delete("fw:rl:" + key)
    return new_session(r, int(t["id"]), member)


def get_session(r, token):
    if not token:
        return None
    s = r.hgetall(_skey(token))
    if not s:
        return None
    slug = r.get(f"fw:teamid:{s['team_id']}")
    t = r.hgetall(f"fw:team:{slug}") if slug else {}
    if not t:
        return None
    return Session(int(s["team_id"]), slug, t["name"], s["member"])


def logout(r, token):
    if token:
        r.delete(_skey(token))


def _expire_sessions(r, team_id):
    keys = r.smembers(f"fw:sesslist:{team_id}")
    if keys:
        r.delete(*keys)
    r.delete(f"fw:sesslist:{team_id}")


def change_password(r, session, data):
    t = r.hgetall(f"fw:team:{session.slug}")
    if not verify_password(str(data.get("current") or ""), t["pw_hash"], t["pw_salt"]):
        raise ApiError(401, "현재 비밀번호가 맞지 않습니다", {"field": "current"})
    h, salt = hash_password(check_password(data.get("new"), "new"))
    r.hset(f"fw:team:{session.slug}", mapping={"pw_hash": h, "pw_salt": salt})
    _expire_sessions(r, session.team_id)


def reset_password(r, slug, new_password):
    t = r.hgetall(f"fw:team:{slug}")
    if not t:
        raise ApiError(404, "없는 팀입니다")
    h, salt = hash_password(check_password(new_password))
    r.hset(f"fw:team:{slug}", mapping={"pw_hash": h, "pw_salt": salt})
    _expire_sessions(r, int(t["id"]))
