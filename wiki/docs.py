"""문서·판 (스펙 6.2·6.4). 모든 함수는 세션 팀 범위로만 동작한다."""
import json
import time

from wiki.errors import ApiError
from wiki.guard import find_secret, validate_body

MAX_DOCS = 2000
PARENT_KIND = {"cloud": None, "instance": "cloud", "area": "instance", "steps": None, "page": None}


def _now():
    return int(time.time())


def _title(body):
    return body.get("name") or body.get("title") or ""


def _doc(conn, team_id, doc_id):
    row = conn.execute("SELECT * FROM docs WHERE id=? AND team_id=?", (doc_id, team_id)).fetchone()
    if not row:
        raise ApiError(404, "문서를 찾을 수 없습니다")
    return row


def _check(kind, body):
    validate_body(kind, body)
    hit = find_secret(body)
    if hit:
        raise ApiError(422, "비밀값처럼 보이는 내용은 저장할 수 없습니다. <개인키> 처럼 자리표시로 바꾸세요.", hit)


def _int(v, field):
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ApiError(422, f"{field} 가 필요합니다", {"field": field})


def get_tree(conn, s):
    rows = conn.execute(
        "SELECT id, kind, parent_id, sort, current_rev, current_body, updated_at FROM docs "
        "WHERE team_id=? AND deleted=0 ORDER BY sort, id", (s.team_id,)).fetchall()
    return {"team": {"slug": s.slug, "name": s.team_name},
            "docs": [{"id": r["id"], "kind": r["kind"], "parent_id": r["parent_id"], "sort": r["sort"],
                      "rev": r["current_rev"], "body": json.loads(r["current_body"]), "updated_at": r["updated_at"]}
                     for r in rows]}


def create_doc(conn, s, data):
    kind = data.get("kind")
    if kind not in PARENT_KIND:
        raise ApiError(422, "알 수 없는 문서 종류입니다", {"field": "kind"})
    body = data.get("body")
    _check(kind, body)
    parent_id = data.get("parent_id")
    need = PARENT_KIND[kind]
    if need:
        if parent_id is None:
            raise ApiError(422, "상위 문서가 필요합니다", {"field": "parent_id"})
        parent = _doc(conn, s.team_id, _int(parent_id, "parent_id"))
        if parent["kind"] != need or parent["deleted"]:
            raise ApiError(422, "상위 문서 종류가 맞지 않습니다", {"field": "parent_id"})
    else:
        parent_id = None
    if kind == "steps" and conn.execute(
            "SELECT 1 FROM docs WHERE team_id=? AND kind='steps' AND deleted=0", (s.team_id,)).fetchone():
        raise ApiError(409, "진행 순서 문서는 팀에 하나만 둘 수 있습니다")
    n, = conn.execute("SELECT count(*) FROM docs WHERE team_id=?", (s.team_id,)).fetchone()
    if n >= MAX_DOCS:
        raise ApiError(422, "팀 문서는 2000개까지입니다")
    raw = json.dumps(body, ensure_ascii=False)
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "INSERT INTO docs(team_id, kind, parent_id, sort, current_rev, current_body, created_at, updated_at) "
            "VALUES(?,?,?,?,1,?,?,?)", (s.team_id, kind, parent_id, int(data.get("sort") or 0), raw, now, now))
        doc_id = cur.lastrowid
        conn.execute("INSERT INTO revisions(doc_id, rev, body, deleted, author, message, created_at) "
                     "VALUES(?,?,?,?,?,?,?)", (doc_id, 1, raw, 0, s.member, str(data.get("message") or ""), now))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"id": doc_id, "rev": 1}


def _new_rev(conn, s, row, base_rev, body, deleted, message):
    """current_rev == base_rev 일 때만 새 판을 만든다. 아니면 409 + 최신 판."""
    raw = json.dumps(body, ensure_ascii=False)
    now = _now()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(
            "UPDATE docs SET current_rev=current_rev+1, current_body=?, deleted=?, updated_at=? "
            "WHERE id=? AND team_id=? AND current_rev=?", (raw, deleted, now, row["id"], s.team_id, base_rev))
        if cur.rowcount == 0:
            conn.execute("ROLLBACK")
            latest = conn.execute(
                "SELECT rev, body, author, created_at FROM revisions WHERE doc_id=? ORDER BY rev DESC LIMIT 1",
                (row["id"],)).fetchone()
            raise ApiError(409, "다른 팀원이 먼저 저장했습니다", {"current": {
                "rev": latest["rev"], "body": json.loads(latest["body"]),
                "author": latest["author"], "created_at": latest["created_at"]}})
        rev = base_rev + 1
        conn.execute("INSERT INTO revisions(doc_id, rev, body, deleted, author, message, created_at) "
                     "VALUES(?,?,?,?,?,?,?)", (row["id"], rev, raw, deleted, s.member, str(message or ""), now))
        conn.execute("COMMIT")
    except ApiError:
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"rev": rev}


def update_doc(conn, s, doc_id, data):
    row = _doc(conn, s.team_id, doc_id)
    body = data.get("body")
    _check(row["kind"], body)
    return _new_rev(conn, s, row, _int(data.get("base_rev"), "base_rev"), body, row["deleted"], data.get("message"))


def delete_doc(conn, s, doc_id, data):
    row = _doc(conn, s.team_id, doc_id)
    if conn.execute("SELECT 1 FROM docs WHERE parent_id=? AND deleted=0", (doc_id,)).fetchone():
        raise ApiError(422, "하위 문서를 먼저 삭제하세요")
    return _new_rev(conn, s, row, _int(data.get("base_rev"), "base_rev"), json.loads(row["current_body"]), 1,
                    data.get("message") or "삭제")


def list_revisions(conn, s, doc_id):
    _doc(conn, s.team_id, doc_id)
    rows = conn.execute("SELECT rev, author, message, created_at, deleted FROM revisions WHERE doc_id=? "
                        "ORDER BY rev DESC", (doc_id,)).fetchall()
    return [dict(r) for r in rows]


def get_revision(conn, s, doc_id, rev):
    _doc(conn, s.team_id, doc_id)
    r = conn.execute("SELECT rev, body, deleted, author, created_at FROM revisions WHERE doc_id=? AND rev=?",
                     (doc_id, rev)).fetchone()
    if not r:
        raise ApiError(404, "그 판이 없습니다")
    return {**dict(r), "body": json.loads(r["body"])}


def restore_doc(conn, s, doc_id, data):
    row = _doc(conn, s.team_id, doc_id)
    old = get_revision(conn, s, doc_id, _int(data.get("rev"), "rev"))
    if row["parent_id"] and conn.execute("SELECT deleted FROM docs WHERE id=?", (row["parent_id"],)).fetchone()[0]:
        raise ApiError(422, "상위 문서가 삭제되어 있습니다. 상위 문서를 먼저 되돌리세요")
    msg = data.get("message") or f"{old['rev']}판으로 되돌림"
    return _new_rev(conn, s, row, _int(data.get("base_rev"), "base_rev"), old["body"], 0, msg)


def list_changes(conn, s, before=None, limit=50):
    limit = max(1, min(int(limit or 50), 100))
    q = ("SELECT r.doc_id, d.kind, r.body, r.rev, r.author, r.message, r.created_at, r.deleted "
         "FROM revisions r JOIN docs d ON d.id=r.doc_id WHERE d.team_id=?")
    args = [s.team_id]
    if before:
        q += " AND r.created_at < ?"
        args.append(int(before))
    q += " ORDER BY r.created_at DESC, r.id DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(q, args).fetchall():
        out.append({"doc_id": r["doc_id"], "kind": r["kind"], "title": _title(json.loads(r["body"])),
                    "rev": r["rev"], "author": r["author"], "message": r["message"],
                    "created_at": r["created_at"], "deleted": r["deleted"]})
    return out


def list_scripts(conn, s):
    rows = conn.execute("SELECT id, path, host, status, keys FROM scripts WHERE team_id=? ORDER BY id",
                        (s.team_id,)).fetchall()
    return [{**dict(r), "keys": json.loads(r["keys"])} for r in rows]


def get_script(conn, s, script_id):
    r = conn.execute("SELECT path, host, status, text FROM scripts WHERE id=? AND team_id=?",
                     (script_id, s.team_id)).fetchone()
    if not r:
        raise ApiError(404, "스크립트를 찾을 수 없습니다")
    return dict(r)
