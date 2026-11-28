"""문서·판 (스펙 6.2·6.4) — Redis. 모든 함수는 세션 팀 범위로만 동작한다."""
import json
import time

import redis

from wiki import auth
from wiki.errors import ApiError
from wiki.guard import find_secret, validate_body

MAX_DOCS = 2000
PARENT_KIND = {"cloud": None, "instance": "cloud", "area": "instance", "steps": None, "page": None}
SECRET_MSG = "비밀값처럼 보이는 내용은 저장할 수 없습니다. <개인키> 처럼 자리표시로 바꾸세요."


def _title(body):
    return body.get("name") or body.get("title") or ""


def _doc(r, team_id, doc_id):
    d = r.hgetall(f"fw:doc:{doc_id}")
    if not d or int(d["team_id"]) != team_id:
        raise ApiError(404, "문서를 찾을 수 없습니다")
    return d


def _check(kind, body):
    validate_body(kind, body)
    hit = find_secret(body)
    if hit:
        raise ApiError(422, SECRET_MSG, hit)


def _message(data, default=""):
    msg = data.get("message")
    msg = default if msg in (None, "") else msg
    if not isinstance(msg, str) or len(msg) > 200:
        raise ApiError(422, "변경 메모는 200자 이하로 입력하세요", {"field": "message"})
    if find_secret(msg, "message"):
        raise ApiError(422, SECRET_MSG, {"field": "message"})
    return msg


def _int(v, field):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(422, f"{field} 가 필요합니다", {"field": field})


def _rev_entry(rev, body_raw, deleted, author, message, ts, access_key=""):
    d = {"rev": rev, "body": body_raw, "deleted": deleted, "author": author,
         "message": message, "created_at": ts}
    if access_key:
        d["access_key"] = access_key
    return json.dumps(d, ensure_ascii=False)


def _enrich_author(author, explicit_key, keybook):
    base_name, parsed_key = auth.parse_author_key(author)
    ak = (explicit_key or parsed_key or "").upper()
    if ak and ak in keybook:
        matched = keybook[ak].get("member") or base_name or author
    else:
        matched = base_name or author
    return ak, matched


def _out(doc_id, d):
    return {"id": doc_id, "kind": d["kind"], "parent_id": int(d["parent_id"]) if d["parent_id"] else None,
            "sort": int(d["sort"]), "rev": int(d["rev"]), "body": json.loads(d["body"]), "updated_at": int(d["updated_at"])}


def get_tree(r, s):
    ids = sorted(int(i) for i in r.smembers(f"fw:docs:{s.team_id}"))
    p = r.pipeline()
    for i in ids:
        p.hgetall(f"fw:doc:{i}")
    rows = [(i, d) for i, d in zip(ids, p.execute()) if d and d.get("deleted") == "0"]
    rows.sort(key=lambda x: (int(x[1]["sort"]), x[0]))
    return {"team": {"slug": s.slug, "name": s.team_name}, "docs": [_out(i, d) for i, d in rows]}


def insert_doc(r, team_id, kind, parent_id, sort, body, author, message, ts=None, access_key=""):
    """검사 없이 새 문서(1판)를 쓴다 — create_doc 와 시드가 사용."""
    ts = ts or int(time.time())
    doc_id = r.incr("fw:seq:doc")
    raw = json.dumps(body, ensure_ascii=False)
    ak = (access_key or auth.parse_author_key(author)[1] or "").upper()
    p = r.pipeline(transaction=True)
    p.hset(f"fw:doc:{doc_id}", mapping={"team_id": team_id, "kind": kind, "parent_id": parent_id or "",
                                         "sort": int(sort or 0), "rev": 1, "body": raw, "deleted": 0,
                                         "created_at": ts, "updated_at": ts})
    p.sadd(f"fw:docs:{team_id}", doc_id)
    if parent_id:
        p.sadd(f"fw:kids:{parent_id}", doc_id)
    if kind == "steps":
        p.set(f"fw:steps:{team_id}", doc_id)
    p.rpush(f"fw:revs:{doc_id}", _rev_entry(1, raw, 0, author, message, ts, ak))
    p.zadd(f"fw:changes:{team_id}", {f"{doc_id}:1": ts * 1000 + doc_id % 1000})
    p.execute()
    return doc_id


def create_doc(r, s, data):
    kind = data.get("kind")
    if kind not in PARENT_KIND:
        raise ApiError(422, "알 수 없는 문서 종류입니다", {"field": "kind"})
    body = data.get("body")
    _check(kind, body)
    message = _message(data)
    parent_id = data.get("parent_id")
    need = PARENT_KIND[kind]
    if need:
        if parent_id is None:
            raise ApiError(422, "상위 문서가 필요합니다", {"field": "parent_id"})
        parent_id = _int(parent_id, "parent_id")
        parent = _doc(r, s.team_id, parent_id)
        if parent["kind"] != need or parent["deleted"] == "1":
            raise ApiError(422, "상위 문서 종류가 맞지 않습니다", {"field": "parent_id"})
    else:
        parent_id = None
    if kind == "steps":
        cur = r.get(f"fw:steps:{s.team_id}")
        if cur and r.hget(f"fw:doc:{cur}", "deleted") == "0":
            raise ApiError(409, "진행 순서 문서는 팀에 하나만 둘 수 있습니다")
    if r.scard(f"fw:docs:{s.team_id}") >= MAX_DOCS:
        raise ApiError(422, "팀 문서는 2000개까지입니다")
    ak = (s.access_key or auth.parse_author_key(s.member)[1] or "").upper()
    doc_id = insert_doc(r, s.team_id, kind, parent_id, data.get("sort"), body, s.member, message, access_key=ak)
    if ak:
        auth.record_access(r, s.team_id, s.member, ak, "create", "", f"{kind}:{_title(body)}")
    return {"id": doc_id, "rev": 1}


def _new_rev(r, s, doc_id, base_rev, body, deleted, message, action="edit"):
    """current rev == base_rev 일 때만 새 판. WATCH 로 동시 저장을 판정하고, 아니면 409 + 최신 판."""
    key = f"fw:doc:{doc_id}"
    raw = json.dumps(body, ensure_ascii=False)
    ak = (s.access_key or auth.parse_author_key(s.member)[1] or "").upper()
    with r.pipeline() as p:
        try:
            p.watch(key)
            d = p.hgetall(key)
            if int(d["rev"]) != base_rev:
                p.unwatch()
                raise _conflict(r, doc_id)
            ts = int(time.time())
            rev = base_rev + 1
            p.multi()
            p.hset(key, mapping={"rev": rev, "body": raw, "deleted": deleted, "updated_at": ts})
            p.rpush(f"fw:revs:{doc_id}", _rev_entry(rev, raw, deleted, s.member, message, ts, ak))
            p.zadd(f"fw:changes:{s.team_id}", {f"{doc_id}:{rev}": ts * 1000 + rev % 1000})
            if d["parent_id"]:
                (p.srem if deleted else p.sadd)(f"fw:kids:{d['parent_id']}", doc_id)
            p.execute()
        except redis.WatchError:
            raise _conflict(r, doc_id)
    if ak:
        auth.record_access(r, s.team_id, s.member, ak, action, "", f"{d['kind']}:{_title(body)} ({rev}판)")
    return {"rev": rev}


def _conflict(r, doc_id):
    last = json.loads(r.lindex(f"fw:revs:{doc_id}", -1))
    return ApiError(409, "다른 팀원이 먼저 저장했습니다", {"current": {
        "rev": last["rev"], "body": json.loads(last["body"]), "author": last["author"], "created_at": last["created_at"]}})


def update_doc(r, s, doc_id, data):
    d = _doc(r, s.team_id, doc_id)
    if d["deleted"] == "1":
        raise ApiError(422, "삭제된 문서입니다. 기록에서 먼저 되돌리세요")
    body = data.get("body")
    _check(d["kind"], body)
    return _new_rev(r, s, doc_id, _int(data.get("base_rev"), "base_rev"), body, 0, _message(data), "edit")


def delete_doc(r, s, doc_id, data):
    d = _doc(r, s.team_id, doc_id)
    if r.scard(f"fw:kids:{doc_id}"):
        raise ApiError(422, "하위 문서를 먼저 삭제하세요")
    return _new_rev(r, s, doc_id, _int(data.get("base_rev"), "base_rev"), json.loads(d["body"]), 1,
                    _message(data, "삭제"), "delete")


def list_revisions(r, s, doc_id):
    _doc(r, s.team_id, doc_id)
    keybook = auth.get_keybook(r, s.team_id)
    out = []
    for raw in reversed(r.lrange(f"fw:revs:{doc_id}", 0, -1)):
        e = json.loads(raw)
        row = {k: e[k] for k in ("rev", "author", "message", "created_at", "deleted")}
        ak, matched = _enrich_author(e.get("author", ""), e.get("access_key", ""), keybook)
        row["access_key"] = ak
        row["matched_user"] = matched
        out.append(row)
    return out


def get_revision(r, s, doc_id, rev):
    _doc(r, s.team_id, doc_id)
    raw = r.lindex(f"fw:revs:{doc_id}", rev - 1) if rev >= 1 else None
    if not raw:
        raise ApiError(404, "그 판이 없습니다")
    e = json.loads(raw)
    keybook = auth.get_keybook(r, s.team_id)
    ak, matched = _enrich_author(e.get("author", ""), e.get("access_key", ""), keybook)
    return {"rev": e["rev"], "body": json.loads(e["body"]), "deleted": e["deleted"],
            "author": e["author"], "access_key": ak, "matched_user": matched, "created_at": e["created_at"]}


def restore_doc(r, s, doc_id, data):
    d = _doc(r, s.team_id, doc_id)
    old = get_revision(r, s, doc_id, _int(data.get("rev"), "rev"))
    if d["parent_id"] and r.hget(f"fw:doc:{d['parent_id']}", "deleted") == "1":
        raise ApiError(422, "상위 문서가 삭제되어 있습니다. 상위 문서를 먼저 되돌리세요")
    msg = _message(data, f"{old['rev']}판으로 되돌림")
    return _new_rev(r, s, doc_id, _int(data.get("base_rev"), "base_rev"), old["body"], 0, msg, "restore")


def list_changes(r, s, before=None, limit=50):
    limit = max(1, min(int(limit or 50), 100))
    hi = f"({int(before) * 1000}" if before else "+inf"
    members = r.zrevrangebyscore(f"fw:changes:{s.team_id}", hi, "-inf", start=0, num=limit)
    keybook = auth.get_keybook(r, s.team_id)
    out = []
    for m in members:
        doc_id, rev = (int(x) for x in m.split(":"))
        e = json.loads(r.lindex(f"fw:revs:{doc_id}", rev - 1))
        ak, matched = _enrich_author(e.get("author", ""), e.get("access_key", ""), keybook)
        out.append({"doc_id": doc_id, "kind": r.hget(f"fw:doc:{doc_id}", "kind"), "title": _title(json.loads(e["body"])),
                    "rev": rev, "author": e["author"], "access_key": ak, "matched_user": matched,
                    "message": e["message"], "created_at": e["created_at"], "deleted": e["deleted"]})
    return out


def add_script(r, team_id, path, host, status, keys, text):
    sid = r.incr("fw:seq:script")
    r.hset(f"fw:script:{sid}", mapping={"team_id": team_id, "path": path, "host": host, "status": status,
                                         "keys": json.dumps(keys, ensure_ascii=False), "text": text})
    r.rpush(f"fw:scripts:{team_id}", sid)
    return sid


def list_scripts(r, s):
    out = []
    for sid in r.lrange(f"fw:scripts:{s.team_id}", 0, -1):
        h = r.hgetall(f"fw:script:{sid}")
        out.append({"id": int(sid), "path": h["path"], "host": h["host"], "status": h["status"],
                    "keys": json.loads(h["keys"])})
    return out


def get_script(r, s, script_id):
    h = r.hgetall(f"fw:script:{script_id}")
    if not h or int(h["team_id"]) != s.team_id:
        raise ApiError(404, "스크립트를 찾을 수 없습니다")
    return {k: h[k] for k in ("path", "host", "status", "text")}
